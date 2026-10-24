"""Contrato real do SDK com emulador oficial. Nunca acessa um projeto de produção."""

from hashlib import sha256
from dataclasses import replace
import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from PIL import Image
import pytest

from rso.cloud_repository import CloudRepository
from rso.excel_generator import ExcelGenerator
from rso.firebase_backend import CHUNK_BYTES, CloudConflict, FirebaseBackend, FirebaseConfig, payload_for
from rso.models import Report, ValidationError
from rso.pdf_generator import PDFGenerator
from rso.project_catalog import ProjectCatalog
from rso.projects import ProjectProfile
from rso.project_state import ProjectChanged, ProjectDeleted, ProjectState

pytestmark = pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"),
                               reason="Requer emulador Firestore local (ver FIREBASE.md)")


@pytest.fixture
def backend():
    host = os.environ["FIRESTORE_EMULATOR_HOST"]
    assert host.startswith(("127.0.0.1:", "localhost:")), "Use somente um emulador local"
    client = firestore.Client(project="demo-rso-santelmo", credentials=AnonymousCredentials())
    result = FirebaseBackend(FirebaseConfig("demo-rso-santelmo", f"test-{uuid4().hex}"), client=client)
    yield result
    client.recursive_delete(client.collection("rso_workspaces").document(result.config.namespace))
    result.close()


def noisy_photo(tmp_path):
    path = tmp_path / "large.jpg"
    Image.frombytes("RGB", (1100, 1100), os.urandom(1100 * 1100 * 3)).save(path, quality=92)
    assert path.stat().st_size > CHUNK_BYTES
    return path


def test_corrected_registration_is_shared_and_recovers_after_cold_start(backend, tmp_path):
    repo = CloudRepository(tmp_path / "before", backend, background=False)
    repo.load_all()
    catalog = ProjectCatalog(repo)
    first = catalog.new_report("sintra")
    second = catalog.new_report("sintra")
    first.activities[0] = "ATIVIDADE PRESERVADA"
    repo.save(first)
    repo.sync_pending(force=True)
    old = CloudRepository(tmp_path / "other-session", backend, background=False)
    old_first = next(r for r in old.load_all() if r.id == second.id)
    ProjectCatalog(old).begin_edit(old_first)
    catalog.begin_edit(first)
    first.registration_draft.update(engineer="ENGENHEIRA CORRIGIDA", crea="CREA-CORRIGIDO")
    catalog.confirm_edit(first)
    repo.sync_pending(force=True)
    old_first.registration_draft["engineer"] = "EDIÇÃO DE SESSÃO ANTIGA"
    with pytest.raises(ProjectChanged):
        ProjectCatalog(old).confirm_edit(old_first)
    cold = CloudRepository(tmp_path / "new-render", backend, background=False)
    rows = cold.load_all()
    assert {r.engineer for r in rows} == {"ENGENHEIRA CORRIGIDA"}
    assert next(r for r in rows if r.id == first.id).activities[0] == "ATIVIDADE PRESERVADA"
    assert ProjectCatalog(cold).new_report("sintra").crea == "CREA-CORRIGIDO"


def test_delete_removes_remote_reports_and_tombstone_blocks_stale_writes(backend, tmp_path):
    repo = CloudRepository(tmp_path / "source", backend, background=False)
    repo.load_all()
    catalog = ProjectCatalog(repo)
    first = catalog.new_report("sintra")
    catalog.new_report("sintra")
    other = catalog.new_report("bosque")
    repo.sync_pending(force=True)
    stale = backend.get_report(first.id)
    catalog.delete("sintra", None)
    assert backend.get_report(first.id) is None
    assert not repo.sync_status(first.id)["status"]
    assert backend.list_projects()["sintra"].deleted
    with pytest.raises(ProjectDeleted):
        backend.put_report(stale["payload"], stale["media"], stale["revision"])
    with pytest.raises(ProjectDeleted):
        repo.save(first)
    cold = CloudRepository(tmp_path / "new-render", backend, background=False)
    assert [r.id for r in cold.load_all()] == [other.id]
    assert "sintra" not in ProjectCatalog(cold).choices()


def test_delete_retries_cleanup_after_network_interruption(backend, tmp_path, monkeypatch):
    repo = CloudRepository(tmp_path / "source", backend, background=False)
    repo.load_all()
    report = ProjectCatalog(repo).new_report("sintra")
    repo.sync_pending(force=True)
    original = backend.purge_reports
    def interrupted(ids):
        raise ConnectionError("interrupção após confirmar a exclusão")
    monkeypatch.setattr(backend, "purge_reports", interrupted)
    ProjectCatalog(repo).delete("sintra", None)
    assert repo.load_all() == [] and backend.get_report(report.id) is not None
    monkeypatch.setattr(backend, "purge_reports", original)
    cold = CloudRepository(tmp_path / "cold", backend, background=False)
    assert cold.load_all() == [] and backend.get_report(report.id) is None
    assert cold.ensure_default_reports() == []


def test_project_transaction_is_idempotent_and_deleted_identity_is_permanent(backend):
    report = Report.new("Casa Sintra")
    profile = ProjectProfile(key="sintra", name=report.tab_name, obra=report.obra,
        address=report.address, cliente=report.cliente, responsavel_tecnico=report.responsavel_tecnico,
        engineer=report.engineer, crea=report.crea, art=report.art, permit=report.permit)
    state = ProjectState("sintra", profile)
    backend.put_project(state, None)
    backend.put_project(state, None)
    with pytest.raises(ProjectChanged):
        backend.put_project(ProjectState("sintra", replace(profile, crea="OUTRO")), None)
    backend.put_project(ProjectState("sintra", deleted=True), state.revision)
    with pytest.raises(ProjectDeleted):
        backend.put_project(state, state.revision)


def test_custom_project_survives_empty_render_cache_and_creates_next_week(backend, tmp_path):
    first = CloudRepository(tmp_path / "registration", backend, background=False)
    first.load_all()
    profile = ProjectProfile(name="Obra cadastrada no Firebase", obra="REFORMA TESTE",
        cliente="CLIENTE TESTE", address="Rua Teste, 10", responsavel_tecnico="ENGª TESTE",
        engineer="ENGENHEIRA TESTE", crea="CREA-TESTE", art="ART-TESTE", permit="ALVARÁ-TESTE")
    original = ProjectCatalog(first).register(profile)
    original.activities[0] = "Atividade da primeira semana"
    first.save(original)
    first.sync_pending(force=True)
    assert first.sync_status(original.id)["status"] == "synced"

    cold = CloudRepository(tmp_path / "empty-cache", backend, background=False)
    restored = cold.load_all()
    assert len(restored) == 1 and restored[0].project_profile == profile
    assert restored[0].activities[0] == "Atividade da primeira semana"
    catalog = ProjectCatalog(cold)
    assert catalog.choices()[profile.key] == profile.name
    second = catalog.new_report(profile.key)
    assert second.activities == [""] * 5 and second.id != original.id
    assert second.crea == profile.crea and second.cliente == profile.cliente
    cold.sync_pending(force=True)
    assert cold.sync_status(second.id)["status"] == "synced"
    assert len(backend.list_reports()) == 2


def test_binary_photo_chunks_round_trip_and_reuse(backend, tmp_path):
    source = noisy_photo(tmp_path)
    digest = backend.upload_photo(source)
    manifest = backend.photos.document(digest).get()
    assert manifest.to_dict()["chunks"] >= 2
    for part in backend.photos.document(digest).collection("chunks").stream():
        assert len(part.to_dict()["data"]) <= CHUNK_BYTES
    target = tmp_path / "restored.jpg"
    backend.download_photo(digest, target)
    assert sha256(target.read_bytes()).hexdigest() == digest
    assert target.read_bytes() == source.read_bytes()
    backend._known_photos.clear()
    backend.upload_photo(source)
    assert backend.photos.document(digest).get().update_time == manifest.update_time


def test_interrupted_photo_has_no_manifest_and_recovers(backend, tmp_path, monkeypatch):
    source = noisy_photo(tmp_path)
    original = firestore.DocumentReference.set

    def fail_second_part(self, *args, **kwargs):
        if self.path.endswith("/chunks/0001"):
            raise ConnectionError("network interruption")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(firestore.DocumentReference, "set", fail_second_part)
    digest = sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ConnectionError):
        backend.upload_photo(source)
    assert not backend.photos.document(digest).get().exists
    monkeypatch.setattr(firestore.DocumentReference, "set", original)
    assert backend.upload_photo(source) == digest
    target = tmp_path / "resumed.jpg"
    backend.download_photo(digest, target)
    assert target.read_bytes() == source.read_bytes()


def test_missing_chunk_does_not_publish_partial_download(backend, tmp_path):
    source = noisy_photo(tmp_path)
    digest = backend.upload_photo(source)
    backend.photos.document(digest).collection("chunks").document("0001").delete()
    target = tmp_path / "existing.jpg"
    target.write_bytes(b"previous cache")
    with pytest.raises(ValidationError):
        backend.download_photo(digest, target)
    assert target.read_bytes() == b"previous cache"


def test_transaction_detects_stale_revision_and_retry_is_idempotent(backend):
    report = Report.new("Casa Sintra")
    before = payload_for(report)
    version = backend.put_report(before, {}, None)
    assert backend.put_report(before, {}, None) == version
    report.activities[0] = "Segunda-feira atualizada"
    updated = backend.put_report(payload_for(report), {}, version)
    assert updated != version
    with pytest.raises(CloudConflict):
        backend.put_report(before, {}, version)
    assert backend.get_report(report.id)["revision"] == updated


def test_cold_restart_recovers_daily_work_photos_and_export(backend, tmp_path):
    first = CloudRepository(tmp_path / "monday", backend, background=False)
    assert first.load_all() == []
    report = Report.new("Casa Sintra")
    report.activities[0] = "Alvenaria de segunda-feira"
    report.add_photo(first.import_photo(noisy_photo(tmp_path), report.id))
    report.photos[0].caption = "Execução de alvenaria"
    first.save(report)
    first.sync_pending(force=True)
    assert first.sync_status(report.id)["status"] == "synced"
    friday = CloudRepository(tmp_path / "fresh-render", backend, background=False)
    recovered, = friday.load_all()
    assert recovered.activities[0] == report.activities[0]
    assert friday.resolve_photo(recovered.photos[0]).read_bytes() == first.resolve_photo(report.photos[0]).read_bytes()
    recovered.activities[4] = "Limpeza de sexta-feira"
    friday.save(recovered)
    friday.sync_pending(force=True)
    assert friday.sync_status(report.id)["status"] == "synced"
    assert PDFGenerator(friday).generate(recovered, tmp_path / "week.pdf").stat().st_size > 1000
    assert ExcelGenerator(friday).generate(recovered, tmp_path / "week.xlsx").stat().st_size > 1000


def test_oversized_report_is_rejected_before_writing(backend):
    report = Report.new("Casa Sintra")
    report.notes = "x" * (900 * 1024)
    with pytest.raises(ValidationError, match="800 KB"):
        backend.put_report(payload_for(report), {}, None)
    assert backend.get_report(report.id) is None


def test_public_client_cannot_read_reports(backend):
    import urllib.error
    import urllib.request
    report = Report.new("Casa Sintra")
    backend.put_report(payload_for(report), {}, None)
    url = (f"http://{os.environ['FIRESTORE_EMULATOR_HOST']}/v1/projects/demo-rso-santelmo/"
           f"databases/(default)/documents/rso_workspaces/{backend.config.namespace}/reports/{report.id}")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(url, timeout=10)
    assert error.value.code == 403
