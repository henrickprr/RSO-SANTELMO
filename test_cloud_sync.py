"""Regressões de perda de dados na fila, reinício, fotos e edições concorrentes."""

from copy import deepcopy
from threading import Event
import time

from PIL import Image
import pytest

from rso.backup import BackupService
from rso.cloud_repository import CloudRepository, open_repository
from rso.firebase_backend import CloudConflict, FirebaseConfig, payload_for, revision_for
from rso.models import Report
from rso.storage import DraftRepository


class Remote:
    def __init__(self):
        self.records, self.photos = {}, {}
        self.before_put = None
        self.unavailable = False
        self.fail_photo = False
        self.lose_ack = False
        self.writes = 0
        self.projects = {}

    def list_projects(self):
        if self.unavailable:
            raise ConnectionError("PRIVATE ERROR CONTENT")
        return deepcopy(self.projects)

    def put_project(self, state, expected):
        from rso.project_state import ProjectChanged, ProjectDeleted
        if self.unavailable:
            raise ConnectionError("PRIVATE ERROR CONTENT")
        current = self.projects.get(state.key)
        if current == state:
            return
        if current and current.deleted:
            raise ProjectDeleted()
        if (current.revision if current else None) != expected:
            raise ProjectChanged()
        self.projects[state.key] = state

    def purge_reports(self, ids):
        for report_id in ids:
            self.records.pop(report_id, None)

    def list_reports(self):
        if self.unavailable:
            raise ConnectionError("PRIVATE ERROR CONTENT")
        return deepcopy(self.records)

    def get_report(self, report_id):
        return deepcopy(self.records.get(report_id))

    def upload_photo(self, path):
        from hashlib import sha256
        if self.fail_photo:
            raise ConnectionError("photo upload interrupted")
        data = path.read_bytes()
        digest = sha256(data).hexdigest()
        self.photos[digest] = data
        return digest

    def download_photo(self, digest, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.photos[digest])

    def put_report(self, payload, media, expected):
        import json
        report_id = json.loads(payload)["id"]
        from rso.project_state import ProjectDeleted, project_key
        state = self.projects.get(project_key(Report.from_dict(json.loads(payload))))
        if state and state.deleted:
            raise ProjectDeleted()
        if self.unavailable:
            raise ConnectionError("PRIVATE ERROR CONTENT")
        if self.before_put:
            callback, self.before_put = self.before_put, None
            callback()
        revision = revision_for(payload)
        old = self.records.get(report_id, {})
        if old.get("revision") == revision:
            return revision
        if old.get("revision") != expected:
            raise CloudConflict()
        self.records[report_id] = dict(payload=payload, media=media, revision=revision)
        self.writes += 1
        if self.lose_ack:
            self.lose_ack = False
            raise ConnectionError("response lost after commit")
        return revision

    def close(self):
        pass


@pytest.fixture
def remote():
    return Remote()


@pytest.fixture
def repo(tmp_path, remote):
    result = CloudRepository(tmp_path / "cache", remote, background=False)
    assert result.load_all() == []
    return result


def add_photo(repo, report, tmp_path):
    source = tmp_path / "foto.jpg"
    Image.new("RGB", (200, 300), "navy").save(source)
    photo = repo.import_photo(source, report.id)
    photo.caption = "Alvenaria"
    report.add_photo(photo)
    return repo.resolve_photo(photo).read_bytes()


def test_offline_project_change_or_delete_is_not_reported_as_completed(repo, remote):
    from rso.project_catalog import ProjectCatalog
    catalog = ProjectCatalog(repo)
    report = catalog.new_report("sintra")
    repo.sync_pending(force=True)
    catalog.begin_edit(report)
    report.registration_draft["cliente"] = "CORREÇÃO AINDA PENDENTE"
    repo.save(report)
    remote.unavailable = True
    with pytest.raises(OSError):
        catalog.confirm_edit(report)
    with pytest.raises(OSError):
        catalog.delete("sintra", None)
    assert report.registration_draft["cliente"] == "CORREÇÃO AINDA PENDENTE"
    assert not repo.project_states and (repo.drafts / f"{report.id}.json").exists()
    remote.unavailable = False
    catalog.confirm_edit(report)
    assert report.cliente == "CORREÇÃO AINDA PENDENTE"


def test_monday_to_friday_survives_loss_of_render_disk(repo, remote, tmp_path):
    report = Report.new("Casa Sintra")
    report.activities[0] = "Alvenaria de segunda"
    original = add_photo(repo, report, tmp_path)
    repo.save(report)
    assert repo.sync_status(report.id)["status"] == "pending"
    repo.sync_pending(force=True)
    assert repo.sync_status(report.id)["status"] == "synced"

    fresh = CloudRepository(tmp_path / "new-render", remote, background=False)
    recovered, = fresh.load_all()
    assert recovered.activities[0] == "Alvenaria de segunda"
    assert fresh.resolve_photo(recovered.photos[0]).read_bytes() == original
    for day in range(1, 5):
        recovered.activities[day] = f"Serviços do dia {day}"
        fresh.save(recovered)
        fresh.sync_pending(force=True)
    again = CloudRepository(tmp_path / "friday", remote, background=False)
    friday, = again.load_all()
    assert friday.activities == ["Alvenaria de segunda", *[f"Serviços do dia {i}" for i in range(1, 5)]]
    assert friday.photos[0].caption == "Alvenaria"
    assert len(remote.records) == len(remote.photos) == 1


def test_partial_input_saved_but_incomplete_photo_never_confirmed(repo, remote, tmp_path):
    report = Report.new("Casa Bosque")
    report.start = "23/"
    add_photo(repo, report, tmp_path)
    remote.fail_photo = True
    repo.save(report)
    repo.sync_pending(force=True)
    assert repo.sync_status(report.id)["status"] == "error"
    assert not remote.records
    remote.fail_photo = False
    repo.sync_pending(force=True)
    assert repo.sync_status(report.id)["status"] == "synced"
    assert '"start":"23/"' in remote.records[report.id]["payload"]


def test_edits_during_upload_remain_pending_then_sync_newest(repo, remote):
    report = Report.new("Casa Sintra")
    report.activities[0] = "Primeiro texto"
    repo.save(report)

    def edit_while_saving():
        report.activities[0] = "Último texto digitado"
        repo.save(report)
    remote.before_put = edit_while_saving
    repo.sync_pending(force=True)
    assert repo.sync_status(report.id)["status"] == "pending"
    assert "Último texto" not in remote.records[report.id]["payload"]
    repo.sync_pending(force=True)
    assert "Último texto" in remote.records[report.id]["payload"]
    assert repo.sync_status(report.id)["status"] == "synced"


def test_lost_ack_is_idempotent(repo, remote):
    report = Report.new("Casa Sintra")
    repo.save(report)
    remote.lose_ack = True
    repo.sync_pending(force=True)
    assert repo.sync_status(report.id)["status"] == "error"
    repo.sync_pending(force=True)
    assert remote.writes == 1
    assert repo.sync_status(report.id)["status"] == "synced"


def test_pending_queue_recovers_after_process_restart(repo, remote):
    report = Report.new("Casa Sintra")
    repo.save(report)
    # Simula interrupção depois da fila e antes do arquivo de leitura.
    (repo.drafts / f"{report.id}.json").unlink()
    resumed = CloudRepository(repo.root, remote, background=False)
    recovered, = resumed.load_all()
    assert payload_for(recovered) == payload_for(report)
    resumed.sync_pending(force=True)
    assert resumed.sync_status(report.id)["status"] == "synced"


def test_cloud_unavailable_with_empty_cache_fails_without_new_reports(tmp_path, remote):
    remote.unavailable = True
    repo = CloudRepository(tmp_path, remote, background=False)
    with pytest.raises(OSError, match="Firebase indisponível") as error:
        repo.load_all()
    assert "PRIVATE" not in str(error.value)
    assert not list(repo.drafts.glob("*.json"))


def test_stale_local_session_cannot_overwrite_another_session(repo):
    report = Report.new("Casa Sintra")
    repo.save(report)
    a, = repo.load_all()
    b, = repo.load_all()
    a.activities[0] = "Primeira sessão"
    repo.save(a)
    b.activities[1] = "Outra sessão"
    with pytest.raises(CloudConflict):
        repo.save(b)
    assert DraftRepository.read(repo.drafts / f"{a.id}.json").activities[0] == "Primeira sessão"
    copy = repo.keep_as_copy(b)
    assert copy.id != b.id and copy.activities[1] == "Outra sessão"


def test_remote_conflict_preserves_both_versions(repo, remote, tmp_path):
    report = Report.new("Casa Sintra")
    repo.save(report)
    repo.sync_pending(force=True)
    other = CloudRepository(tmp_path / "other-device", remote, background=False)
    stale, = other.load_all()
    report.activities[0] = "Edição confirmada"
    repo.save(report)
    repo.sync_pending(force=True)
    stale.activities[1] = "Edição concorrente"
    other.save(stale)
    other.sync_pending(force=True)
    assert other.sync_status(stale.id)["status"] == "conflict"
    copy = other.keep_as_copy(stale)
    other.sync_pending(force=True)
    assert "Edição confirmada" in remote.records[report.id]["payload"]
    assert "Edição concorrente" in remote.records[copy.id]["payload"]
    assert other.sync_status(copy.id)["status"] == "synced"


def test_backup_restore_is_enqueued_for_firebase(repo, remote, tmp_path):
    report = Report.new("Casa Bosque")
    add_photo(repo, report, tmp_path)
    repo.save(report)
    repo.sync_pending(force=True)
    archive = BackupService(repo).create(tmp_path / "backup.zip")
    copies = BackupService(repo).restore(archive)
    assert len(copies) == 1 and copies[0].id != report.id
    repo.sync_pending(force=True)
    assert copies[0].id in remote.records
    assert len(remote.photos) == 1  # A imagem idêntica é reaproveitada.


def test_background_autosave_coalesces_changes_and_needs_no_button(tmp_path, remote):
    done = Event()
    original = remote.put_report
    def put(*args):
        value = original(*args)
        done.set()
        return value
    remote.put_report = put
    repo = CloudRepository(tmp_path, remote)
    repo.load_all()
    report = Report.new("Casa Sintra")
    try:
        for index in range(20):
            report.activities[0] = f"Texto {index}"
            repo.save(report)
        assert done.wait(5), "O autosave não iniciou sem clique manual"
        deadline = time.monotonic() + 2
        while repo.sync_status(report.id)["status"] != "synced" and time.monotonic() < deadline:
            time.sleep(.01)
        assert repo.sync_status(report.id)["status"] == "synced"
        assert remote.writes == 1 and "Texto 19" in remote.records[report.id]["payload"]
    finally:
        repo.close()


def test_local_drafts_migrate_without_editing_and_work_is_isolated(tmp_path, remote):
    local = DraftRepository(tmp_path)
    a, b = Report.new("Casa Sintra"), Report.new("Casa Bosque")
    a.activities[0], b.activities[0] = "Só Sintra", "Só Bosque"
    local.save(a)
    local.save(b)
    cloud = CloudRepository(tmp_path, remote, background=False)
    assert len(cloud.load_all()) == 2
    cloud.sync_pending(force=True)
    assert "Só Sintra" in remote.records[a.id]["payload"]
    assert "Só Bosque" not in remote.records[a.id]["payload"]


def test_configuration_never_silently_falls_back_to_local(tmp_path, monkeypatch):
    monkeypatch.setenv("RSO_BACKEND", "firebase")
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    with pytest.raises(RuntimeError, match="FIREBASE_PROJECT_ID"):
        open_repository(tmp_path)
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-rso-santelmo")
    monkeypatch.setenv("FIREBASE_DATABASE_ID", "paid-second-db")
    with pytest.raises(RuntimeError, match="cota gratuita"):
        FirebaseConfig.from_env()


def test_quota_error_never_confirms_save_and_does_not_leak_api_details(repo, remote):
    from google.api_core.exceptions import ResourceExhausted
    def quota(*args):
        raise ResourceExhausted("PRIVATE token/credential details")
    remote.put_report = quota
    report = Report.new("Casa Sintra")
    repo.save(report)
    repo.sync_pending(force=True)
    state = repo.sync_status(report.id)
    assert state["status"] == "error" and "Cota gratuita" in state["error"]
    assert "PRIVATE" not in state["error"]
    assert repo.due[report.id] > time.monotonic() + 290
    assert not remote.records


def test_simultaneous_initial_sessions_do_not_duplicate_default_reports(repo):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = list(pool.map(lambda _: repo.ensure_default_reports(), range(2)))
    assert len(list(repo.drafts.glob("*.json"))) == 4
    assert {r.id for r in batches[0]} == {r.id for r in batches[1]}


def test_ui_does_not_confirm_cloud_save_while_browser_still_uploads(repo):
    from types import SimpleNamespace
    from rso.ui import ObraTab
    report = Report.new("Casa Sintra")
    repo.save(report)
    repo.sync_pending(force=True)
    page = SimpleNamespace(overlay=[], update=lambda: None, open=lambda _: None)
    tab = ObraTab(page, report, repo)
    assert "Salvo no Firebase" in tab.status.value
    tab.set_importing(True)
    assert "Recebendo fotos" in tab.status.value
    assert "Salvo no Firebase" not in tab.status.value
    tab.set_importing(False)
    assert "Salvo no Firebase" in tab.status.value
