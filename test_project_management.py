"""Correção sem perda do diário e exclusão sem ressurreição por abas antigas."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import fitz
from openpyxl import load_workbook
from PIL import Image
import pytest

from rso.backup import BackupService
from rso.excel_generator import ExcelGenerator
from rso.models import ValidationError
from rso.pdf_generator import PDFGenerator
from rso.project_catalog import ProjectCatalog
from rso.project_state import ProjectChanged, ProjectDeleted, ProjectState
from rso.projects import FIXED_FIELDS, ProjectProfile
from rso.storage import DraftRepository
from rso.ui import ObraTab, RSOApp


@pytest.fixture
def data(tmp_path):
    repo = DraftRepository(tmp_path / "data")
    catalog = ProjectCatalog(repo)
    profile = ProjectProfile(name="Casa teste", obra="REFORMA TESTE", cliente="CLIENTE ORIGINAL",
        address="Rua Teste, 10", responsavel_tecnico="RESPONSÁVEL TESTE", engineer="ENGENHEIRO TESTE",
        crea="CREA-123", art="ART-123", permit="ALVARÁ-123")
    first = catalog.register(profile)
    first.activities[0] = "Alvenaria preservada"
    repo.save(first)
    second = catalog.new_report(profile.key)
    return repo, catalog, first, second


def test_correction_applies_to_existing_and_future_weeks_without_losing_daily_data(data, tmp_path):
    repo, catalog, first, second = data
    catalog.begin_edit(first)
    first.registration_draft.update(cliente="CLIENTE CORRIGIDO", crea="CREA-CORRIGIDO",
                                    tab_name="Casa corrigida")
    repo.save(first)
    catalog.confirm_edit(first)
    reopened = DraftRepository(repo.root)
    reports = reopened.load_all()
    assert len(reports) == 2 and {r.cliente for r in reports} == {"CLIENTE CORRIGIDO"}
    assert {r.crea for r in reports} == {"CREA-CORRIGIDO"}
    assert next(r for r in reports if r.id == first.id).activities[0] == "Alvenaria preservada"
    # Outra aba antiga pode salvar dados semanais; não pode restaurar o cadastro antigo.
    second.activities[1] = "Serviço da outra aba"
    repo.save(second)
    assert second.cliente == "CLIENTE CORRIGIDO"
    third = ProjectCatalog(reopened).new_report(first.project_key)
    assert third.tab_name == "Casa corrigida" and third.activities == [""] * 5
    for generator, suffix in ((PDFGenerator, "pdf"), (ExcelGenerator, "xlsx")):
        path = generator(repo).generate(second, tmp_path / f"corrigido.{suffix}")
        if suffix == "pdf":
            with fitz.open(path) as doc:
                text = "\n".join(p.get_text() for p in doc)
        else:
            book = load_workbook(path)
            text = "\n".join(str(c.value) for row in book["RSO"] for c in row if c.value is not None)
            book.close()
        assert "CLIENTE CORRIGIDO" in text and "CREA-CORRIGIDO" in text
        assert "CLIENTE ORIGINAL" not in text


def test_incomplete_correction_survives_restart_and_cannot_be_exported(data, tmp_path):
    repo, catalog, first, _ = data
    catalog.begin_edit(first)
    first.registration_draft["crea"] = ""
    repo.save(first)
    loaded = next(r for r in DraftRepository(repo.root).load_all() if r.id == first.id)
    assert loaded.registration_draft["crea"] == "" and loaded.crea == "CREA-123"
    with pytest.raises(ValueError):
        catalog.confirm_edit(loaded)
    with pytest.raises(ValidationError, match="Fixar Informações"):
        PDFGenerator(repo).generate(loaded, tmp_path / "invalid.pdf")
    assert not (tmp_path / "invalid.pdf").exists()


def test_report_write_failure_after_profile_commit_keeps_correction_for_retry(data, monkeypatch):
    repo, catalog, first, _ = data
    catalog.begin_edit(first)
    first.registration_draft["cliente"] = "CORREÇÃO CONFIRMADA"
    original_save = repo.save
    def fail(report):
        raise OSError("disk unavailable")
    monkeypatch.setattr(repo, "save", fail)
    with pytest.raises(OSError):
        catalog.confirm_edit(first)
    assert first.registration_draft["cliente"] == "CORREÇÃO CONFIRMADA"
    monkeypatch.setattr(repo, "save", original_save)
    catalog.confirm_edit(first)
    assert first.registration_draft is None and first.cliente == "CORREÇÃO CONFIRMADA"


def test_stale_correction_does_not_replace_a_newer_registration(data):
    repo, catalog, first, second = data
    catalog.begin_edit(first)
    catalog.begin_edit(second)
    first.registration_draft["cliente"] = "CORREÇÃO NOVA"
    catalog.confirm_edit(first)
    second.registration_draft["cliente"] = "CORREÇÃO ANTIGA"
    with pytest.raises(ProjectChanged):
        catalog.confirm_edit(second)
    assert second.registration_draft["cliente"] == "CORREÇÃO ANTIGA"
    assert catalog.new_report(first.project_key).cliente == "CORREÇÃO NOVA"


def test_original_projects_can_be_corrected_and_backup_keeps_the_override(tmp_path):
    repo = DraftRepository(tmp_path / "original")
    catalog = ProjectCatalog(repo)
    sintra = catalog.new_report("sintra")
    catalog.begin_edit(sintra)
    sintra.registration_draft["engineer"] = "ENGENHEIRA CORRIGIDA"
    catalog.confirm_edit(sintra)
    archive = BackupService(repo).create(tmp_path / "backup.zip")
    restored = DraftRepository(tmp_path / "restored")
    BackupService(restored).restore(archive)
    assert ProjectCatalog(restored).new_report("sintra").engineer == "ENGENHEIRA CORRIGIDA"


def test_delete_removes_all_weeks_blocks_stale_saves_and_preserves_other_work(data, tmp_path):
    repo, catalog, first, second = data
    other = catalog.new_report("sintra")
    source = tmp_path / "image.jpg"
    Image.new("RGB", (80, 90), "green").save(source)
    first.add_photo(repo.import_photo(source, first.id))
    repo.save(first)
    photo_path = repo.resolve_photo(first.photos[0])
    catalog.delete(first.project_key, None)
    assert {r.id for r in repo.load_all()} == {other.id}
    assert first.project_key not in catalog.choices() and not photo_path.exists()
    assert not (repo.drafts / f"{first.id}.json.bak").exists()
    with pytest.raises(ProjectDeleted):
        repo.save(second)
    with pytest.raises(ValidationError):
        catalog.new_report(first.project_key)
    reopened = DraftRepository(repo.root)
    assert first.project_key not in ProjectCatalog(reopened).choices()


def test_delete_does_not_remove_shared_local_photo_and_old_backup_restores_as_new_work(data, tmp_path):
    repo, catalog, first, _ = data
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (80, 90), "green").save(source)
    first.add_photo(repo.import_photo(source, first.id))
    repo.save(first)
    other = catalog.new_report("sintra")
    other.photos = deepcopy(first.photos)
    repo.save(other)
    archive = BackupService(repo).create(tmp_path / "before-delete.zip")
    path = repo.resolve_photo(first.photos[0])
    catalog.delete(first.project_key, None)
    assert path.exists()
    recovered = BackupService(repo).restore(archive)
    custom = [r for r in recovered if r.project_key != "sintra"]
    assert len({r.project_key for r in custom}) == 1
    assert custom[0].project_key != first.project_key
    assert repo.project_states[first.project_key].deleted
    assert catalog.new_report(custom[0].project_key).cliente == "CLIENTE ORIGINAL"


def test_delete_everything_stays_empty_after_restart(tmp_path):
    repo = DraftRepository(tmp_path)
    repo.ensure_default_reports()
    catalog = ProjectCatalog(repo)
    for key in list(catalog.choices()):
        catalog.delete(key, None)
    reopened = DraftRepository(tmp_path)
    assert reopened.load_all() == reopened.ensure_default_reports() == []
    assert ProjectCatalog(reopened).choices() == {}


def test_checkbox_unlocks_header_and_footer_then_fixes_corrected_values(data):
    repo, _, first, _ = data
    page = SimpleNamespace(overlay=[], web=False, open=lambda c: None, update=lambda: None)
    view = ObraTab(page, first, repo)

    async def exercise():
        view.lock_information.value = False
        await view.toggle_registration(SimpleNamespace(control=view.lock_information))
        for name in FIXED_FIELDS - {"template"}:
            assert not view.fields[name].disabled and view.fields[name].on_change is not None
        control = view.fields["cliente"]
        control.value = "NOME CORRIGIDO PELA UI"
        await control.on_change(SimpleNamespace(control=control))
        view.lock_information.value = True
        await view.toggle_registration(SimpleNamespace(control=view.lock_information))
        assert first.registration_draft is None and first.cliente == control.value
        assert control.disabled and view.fields["crea"].disabled
    asyncio.run(exercise())


def test_delete_confirmation_can_be_cancelled_without_mutation(data):
    repo, _, first, second = data
    opened, closed = [], []
    page = SimpleNamespace(overlay=[], web=False, open=opened.append, close=closed.append,
                           update=lambda: None)
    app = RSOApp(page, repo)
    app.add_tab(first)
    app.add_tab(second)
    asyncio.run(app.delete_project(first))
    dialog = opened[-1]
    assert "2 relatório(s)" in dialog.content.content.value
    dialog.actions[0].on_click(None)
    assert closed == [dialog] and len(repo.load_all()) == 2
    assert not repo.project_states


def test_cancel_correction_restores_confirmed_header_without_losing_weekly_data(data):
    repo, catalog, first, _ = data
    catalog.begin_edit(first)
    first.registration_draft["cliente"] = "CORREÇÃO DESCARTADA"
    repo.save(first)
    page = SimpleNamespace(overlay=[], web=False, open=lambda c: None, update=lambda: None)
    view = ObraTab(page, first, repo)
    asyncio.run(view.cancel_registration(None))
    assert first.registration_draft is None and first.cliente == "CLIENTE ORIGINAL"
    assert first.activities[0] == "Alvenaria preservada"
    assert view.fields["cliente"].disabled and not view.cancel_registration_button.visible


def test_project_state_rejects_cross_project_profile(data):
    _, _, report, _ = data
    with pytest.raises(ValueError):
        ProjectState("sintra", report.project_profile)
    state = ProjectState(report.project_key, report.project_profile)
    bad = state.to_dict()
    bad["profile"] = replace(report.project_profile, cliente="OUTRO").__dict__
    with pytest.raises(ValueError):
        ProjectState.from_dict(bad)
