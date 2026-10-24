"""Cadastros duráveis e independência dos relatórios de obras adicionadas na UI."""

from concurrent.futures import ThreadPoolExecutor
import asyncio
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import fitz
import flet as ft
from openpyxl import load_workbook
import pytest

from rso.backup import BackupService
from rso.excel_generator import ExcelGenerator
from rso.models import Report, ResourceRow, ValidationError
from rso.pdf_generator import PDFGenerator
from rso.project_catalog import ProjectCatalog
from rso.projects import FIXED_FIELDS, ProjectProfile
from rso.storage import DraftRepository
from rso.ui import ObraTab, RSOApp


@pytest.fixture
def profile():
    return ProjectProfile(name="Casa Ipê", obra="REFORMA RESIDENCIAL - CASA IPÊ",
        cliente="CLIENTE DE TESTE", address="Rua Teste, 100 - Teresina (PI)",
        responsavel_tecnico="ENGª ANA TESTE", engineer="ANA TESTE",
        crea="TESTE-1234", art="ART-TESTE-5678", permit="ALVARÁ-TESTE-90")


def test_registration_survives_restart_and_new_week_has_no_shared_state(tmp_path, profile):
    repo = DraftRepository(tmp_path)
    first = ProjectCatalog(repo).register(profile)
    first.activities[0] = "Execução de alvenaria"
    first.materials = "Cimento"
    first.employees[0].quantity = "2"
    first.equipment.append(ResourceRow(description="Betoneira", quantity="1"))
    repo.save(first)
    restarted = DraftRepository(tmp_path)
    catalog = ProjectCatalog(restarted)
    assert catalog.choices()[profile.key] == profile.name
    second = catalog.new_report(profile.key)
    assert first.id != second.id and first.project_key == second.project_key
    assert second.project_profile == profile
    assert second.activities == [""] * 5 and not second.materials
    assert not second.photos and not second.equipment and second.employees[0].quantity == "0"
    second.activities[1] = "Serviço independente"
    assert first.activities[1] == ""
    assert len(restarted.load_all()) == 2
    with pytest.raises(FrozenInstanceError):
        second.project_profile.crea = "OUTRO"


def test_custom_registration_is_readonly_and_weekly_inputs_remain_editable(tmp_path, profile):
    repo = DraftRepository(tmp_path)
    report = ProjectCatalog(repo).register(profile)
    view = ObraTab(SimpleNamespace(overlay=[], web=False), report, repo)
    for name in FIXED_FIELDS - {"template"}:
        assert view.fields[name].read_only and view.fields[name].disabled
        assert view.fields[name].on_change is None
    assert not view.fields["start"].read_only
    assert not view.fields["evolution"].read_only
    # Um campo semanal alterado fora da UI não pode substituir o cadastro salvo.
    report.cliente, report.engineer = "ERRADO", "ERRADO"
    repo.save(report)
    restored = repo.load_all()[0]
    assert restored.cliente == profile.cliente and restored.engineer == profile.engineer


@pytest.mark.parametrize("name", ["CASA IPE", " casa   ipê "])
def test_duplicate_names_do_not_create_extra_report(tmp_path, profile, name):
    repo = DraftRepository(tmp_path)
    catalog = ProjectCatalog(repo)
    catalog.register(profile)
    with pytest.raises(ValidationError, match="já está cadastrada"):
        catalog.register(replace(profile, name=name, key="custom_00000000000000000000000000000001"))
    assert len(repo.load_all()) == 1


def test_builtin_name_and_concurrent_registration_are_not_duplicated(tmp_path, profile):
    repo = DraftRepository(tmp_path)
    catalog = ProjectCatalog(repo)
    with pytest.raises(ValidationError, match="já está cadastrada"):
        catalog.register(replace(profile, name="casa sintra"))

    def register():
        try:
            return catalog.register(profile).id
        except ValidationError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: register(), range(2)))
    assert sum(value is not None for value in results) == 1
    assert len(repo.load_all()) == 1


def test_backup_restores_catalog_once_and_supports_new_reports(tmp_path, profile):
    source = DraftRepository(tmp_path / "source")
    catalog = ProjectCatalog(source)
    catalog.register(profile)
    catalog.new_report(profile.key)
    archive = BackupService(source).create(tmp_path / "backup.zip")
    restored = DraftRepository(tmp_path / "restored")
    BackupService(restored).restore(archive)
    new_catalog = ProjectCatalog(restored)
    assert len(new_catalog.choices()) == 5
    assert new_catalog.choices()[profile.key] == profile.name
    new = new_catalog.new_report(profile.key)
    assert new.tab_name == profile.name and new.project_profile == profile
    assert new.art == profile.art and new.permit == profile.permit


def test_export_uses_custom_header_and_footer_in_pdf_and_excel(tmp_path, profile):
    repo = DraftRepository(tmp_path / "data")
    report = ProjectCatalog(repo).register(profile)
    report.cliente, report.crea = "ERRADO", "ERRADO"
    pdf = PDFGenerator(repo).generate(report, tmp_path / "new.pdf")
    xlsx = ExcelGenerator(repo).generate(report, tmp_path / "new.xlsx")
    with fitz.open(pdf) as document:
        pdf_text = "\n".join(page.get_text() for page in document)
    workbook = load_workbook(xlsx)
    excel_text = "\n".join(str(cell.value) for row in workbook["RSO"] for cell in row
                           if cell.value is not None)
    workbook.close()
    for text in (pdf_text, excel_text):
        for value in (profile.obra, profile.cliente, profile.address, profile.responsavel_tecnico,
                      profile.engineer, profile.crea, profile.art, profile.permit):
            assert value in text
        assert "ERRADO" not in text and "JUDSON E LAURA" not in text


def test_legacy_payload_without_profile_is_still_supported():
    payload = Report.new("Casa Bosque").to_dict()
    payload.pop("project_profile")
    restored = Report.from_dict(payload)
    assert restored.project_profile is None and restored.project_key == "bosque"


def test_mismatched_or_invalid_registration_is_rejected(profile):
    payload = Report.new(profile.name, profile=profile).to_dict()
    payload["project_key"] = "sintra"
    with pytest.raises(ValueError, match="outra obra"):
        Report.from_dict(payload)
    with pytest.raises(ValueError):
        replace(profile, crea="")
    with pytest.raises(ValueError):
        replace(profile, key="../sintra")


def test_dialog_accepts_corrected_fields_after_required_field_error(tmp_path, profile):
    opened = []
    page = SimpleNamespace(overlay=[], height=900, web=False, open=opened.append,
                           close=lambda c: None, update=lambda: None)
    repo = DraftRepository(tmp_path)
    app = RSOApp(page, repo)

    def children(control):
        yield control
        for child in control._get_children():
            yield from children(child)

    async def exercise():
        await app.add_project(None)
        dialog = opened[-1]
        inputs = [c for c in children(dialog) if isinstance(c, ft.TextField)]
        save = next(c for c in children(dialog) if isinstance(c, ft.FilledButton))
        await save.on_click(None)
        assert inputs[0].error_text and not repo.load_all()
        values = (profile.name, profile.obra, profile.cliente, profile.address,
                  profile.responsavel_tecnico, profile.engineer, profile.crea,
                  profile.art, profile.permit)
        for control, value in zip(inputs, values):
            control.value = value
        await save.on_click(None)
        assert len(repo.load_all()) == 1
        assert repo.load_all()[0].cliente == profile.cliente
        assert app.tabs.selected_index == 0 and len(app.views) == 1

    asyncio.run(exercise())
