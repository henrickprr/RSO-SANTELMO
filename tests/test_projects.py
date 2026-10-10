from types import SimpleNamespace

import fitz
import pytest

from rso.models import Report
from rso.pdf_generator import PDFGenerator
from rso.projects import PROJECTS
from rso.storage import DraftRepository
from rso.ui import ObraTab


@pytest.mark.parametrize("key", list(PROJECTS))
def test_each_work_has_its_own_fixed_registration(key):
    profile = PROJECTS[key]
    report = Report.new(profile["name"])
    assert report.project_key == key
    assert report.cliente == profile["cliente"]
    assert report.art == profile["art"] and report.permit == profile["permit"]
    assert report.crea == "1915794803" and report.engineer == "DANILO FONSECA"
    assert profile["name"].upper() in report.obra
    assert not report.activities[0] and not report.photos


def test_fixed_fields_are_readonly_but_explicit_exceptions_remain_editable(tmp_path):
    page = SimpleNamespace(overlay=[], web=False)
    repo = DraftRepository(tmp_path)
    sintra = ObraTab(page, Report.new("Casa Sintra"), repo)
    atrio = ObraTab(page, Report.new("Casa Átrio"), repo)
    for field in ("cliente", "obra", "responsavel_tecnico", "engineer", "crea", "art", "permit"):
        assert sintra.fields[field].read_only
        assert sintra.fields[field].disabled
        assert sintra.fields[field].on_change is None
    assert not sintra.fields["address"].read_only
    assert not atrio.fields["cliente"].read_only
    assert not sintra.fields["start"].read_only
    assert not sintra.fields["evolution"].read_only


def test_old_draft_replaces_registration_without_changing_weekly_data(tmp_path):
    report = Report.new("Casa Sintra")
    raw = report.to_dict()
    raw.pop("project_key")
    raw["cliente"], raw["art"] = "OUTRO CLIENTE", "ART ERRADA"
    raw["activities"][0] = "Atividade semanal preservada"
    raw["address"] = "Endereço informado pelo usuário"
    restored = Report.from_dict(raw)
    assert restored.cliente == "JUDSON E LAURA"
    assert restored.art == "CE20251740545"
    assert restored.activities[0] == "Atividade semanal preservada"
    assert restored.address == raw["address"]
    repo = DraftRepository(tmp_path)
    repo.save(restored)
    assert repo.load_all()[0].address == raw["address"]


def test_atrio_client_and_addresses_survive_serialization_and_restore():
    report = Report.new("Casa Átrio")
    report.cliente, report.address = "Cliente preenchido", "Endereço preenchido"
    restored = Report.from_dict(report.to_dict())
    restored.tab_name += " (restaurada)"
    again = Report.from_dict(restored.to_dict())
    assert again.project_key == "atrio"
    assert again.cliente == "Cliente preenchido"
    assert again.address == "Endereço preenchido"
    assert again.permit == "139/2026"


def test_export_uses_correct_fixed_identity_even_if_report_was_modified(tmp_path):
    report = Report.new("Casa Sintra")
    report.cliente, report.art, report.crea = "DADOS INDEVIDOS", "ART ERRADA", "000"
    result = PDFGenerator(DraftRepository(tmp_path / "data")).generate(report, tmp_path / "sintra.pdf")
    with fitz.open(result) as doc:
        text = "\n".join(page.get_text() for page in doc)
    assert "JUDSON E LAURA" in text and "CE20251740545" in text and "1915794803" in text
    assert "DADOS INDEVIDOS" not in text and "ART ERRADA" not in text
