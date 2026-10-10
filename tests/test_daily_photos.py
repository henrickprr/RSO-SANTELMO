"""A regra diária vale para UI, JSON e os dois formatos de exportação."""

import asyncio
import json
from types import SimpleNamespace

import fitz
from openpyxl import load_workbook
import pytest

from rso.excel_generator import ExcelGenerator
from rso.layout import LayoutEngine
from rso.models import DAYS, Photo, Report, ValidationError
from rso.pdf_generator import PDFGenerator
from rso.storage import DraftRepository
from rso.ui import ObraTab
from tools.demo import load_demo


@pytest.fixture
def repo(tmp_path):
    return DraftRepository(tmp_path / "daily")


@pytest.fixture
def daily(repo):
    return load_demo(repo)


@pytest.mark.parametrize("count", [0, 1, 3, 5, 6])
@pytest.mark.parametrize("generator", [PDFGenerator, ExcelGenerator])
def test_both_exporters_reject_invalid_daily_count(repo, daily, tmp_path, count, generator):
    path = daily.photos[0].path
    daily.photos = [p for p in daily.photos if p.day != 0]
    daily.photos.extend(Photo(path, day=0) for _ in range(count))
    output = tmp_path / "invalid"
    with pytest.raises(ValidationError, match=f"Segunda-feira \\({count} fotos\\)"):
        generator(repo).generate(daily, output)
    assert not output.exists()


def test_two_and_four_photos_are_valid(daily):
    assert [len(daily.photos_for_day(d)) for d in range(5)] == [2, 4, 2, 2, 2]
    daily.validate()


def test_cap_does_not_modify_photo_on_rejected_move(daily):
    monday_photo = daily.photos_for_day(0)[0]
    with pytest.raises(ValidationError, match="já contém 4 fotos"):
        daily.assign_photo(monday_photo, 1)
    assert monday_photo.day == 0
    with pytest.raises(ValidationError):
        daily.add_photo(Photo(monday_photo.path), 1)
    assert len(daily.photos_for_day(1)) == 4


def test_old_draft_keeps_photos_unassigned_until_user_selects_day(repo, daily):
    raw = daily.to_dict()
    for photo in raw["photos"]:
        del photo["day"]
    target = repo.drafts / f"{daily.id}.json"
    target.write_text(json.dumps({"schema_version": 1, "report": raw}), encoding="utf-8")
    restored = repo.load_all()[0]
    assert len(restored.photos) == 12
    assert all(photo.day is None for photo in restored.photos)
    with pytest.raises(ValidationError, match="Indique o dia"):
        restored.validate()
    repo.save(restored)
    assert json.loads(target.read_text())["schema_version"] == 2
    assert len(repo.load_all()[0].photos) == 12


def test_odd_draft_can_be_saved_without_losing_day_or_caption(repo, daily):
    daily.photos.remove(daily.photos_for_day(0)[0])
    daily.photos_for_day(0)[0].caption = "Legenda preservada"
    repo.save(daily)
    restored = repo.load_all()[0]
    assert len(restored.photos_for_day(0)) == 1
    assert restored.photos_for_day(0)[0].caption == "Legenda preservada"


def test_partial_period_checks_only_days_in_period(daily):
    daily.start = "30/09/2026"
    daily.activities[:2] = ["", ""]
    with pytest.raises(ValidationError, match="fora do período"):
        daily.validate()
    daily.photos = [p for p in daily.photos if p.day >= 2]
    daily.validate()


@pytest.mark.parametrize("day", [-1, 5, "0", True, 1.5])
def test_invalid_day_is_rejected(daily, day):
    raw = daily.to_dict()
    raw["photos"][0]["day"] = day
    with pytest.raises(ValidationError, match="Dia da foto inválido"):
        Report.from_dict(raw)


def test_exported_days_are_chronological_even_when_imported_out_of_order(repo, daily, tmp_path):
    daily.photos.reverse()
    for photo in daily.photos:
        photo.caption = f"MARCADOR-DIA-{photo.day}"
    plan = LayoutEngine(daily, repo).build()
    labels = [b.text for page in plan for b in page.boxes if b.text.startswith("MARCADOR-DIA")]
    assert labels == sorted(labels)
    pdf = PDFGenerator(repo).generate(daily, tmp_path / "daily.pdf", plan)
    xlsx = ExcelGenerator(repo).generate(daily, tmp_path / "daily.xlsx", plan)
    with fitz.open(pdf) as doc:
        text = "\n".join(page.get_text() for page in doc)
        for day in DAYS:
            assert day.upper() in text
        assert all("ENGENHEIRO RESPONSÁVEL" in p.get_text() for p in list(doc)[1:])
    workbook = load_workbook(xlsx)
    values = [str(c.value) for sheet in workbook if sheet.sheet_state == "visible"
              for row in sheet for c in row if c.value is not None]
    for day in DAYS:
        assert any(day.upper() in value for value in values)


class FakePage:
    web = False

    def __init__(self):
        self.overlay, self.dialogs = [], []

    def update(self):
        pass

    def open(self, dialog):
        self.dialogs.append(dialog)


def test_ui_rejects_entire_batch_above_remaining_capacity(repo, daily):
    page = FakePage()
    tab = ObraTab(page, daily, repo)
    tab.picker_day = 0  # Já contém duas fotos; só cabem mais duas.
    event = SimpleNamespace(files=[SimpleNamespace(path="not-read.jpg", name=str(i)) for i in range(3)])
    asyncio.run(tab.on_photos_selected(event))
    assert len(daily.photos_for_day(0)) == 2
    assert page.dialogs
    assert not tab.importing_photos


def test_ui_import_captures_day_and_does_not_touch_another_work(repo, daily):
    page = FakePage()
    tab = ObraTab(page, daily, repo)
    other = Report.new("Outra obra")
    other_tab = ObraTab(page, other, repo)
    source = repo.resolve_photo(daily.photos[0])
    tab.picker_day = 0
    tab.upload_day.value = "4"  # Alterar a seleção não muda o dia já capturado pelo FilePicker.
    event = SimpleNamespace(files=[SimpleNamespace(path=str(source), name=f"foto-{i}.jpg") for i in range(2)])
    asyncio.run(tab.on_photos_selected(event))
    assert len(daily.photos_for_day(0)) == 4
    assert len(daily.photos_for_day(4)) == 2
    assert not other_tab.report.photos
    assert not tab.importing_photos
    restored = DraftRepository.read(repo.drafts / f"{daily.id}.json")
    assert len(restored.photos_for_day(0)) == 4


def test_concurrent_web_uploads_keep_day_and_ignore_duplicate_completion(repo, daily):
    page = FakePage()
    page.web = True
    tab = ObraTab(page, daily, repo)
    source = repo.resolve_photo(daily.photos[0]).read_bytes()
    for name in ("a.jpg", "b.jpg"):
        temporary = repo.uploads / name
        temporary.write_bytes(source)
        tab.pending_uploads[name] = (temporary, 0)
    tab.set_importing(True)

    async def complete():
        events = [SimpleNamespace(file_name=name, error=None, progress=1)
                  for name in ("b.jpg", "b.jpg", "a.jpg")]
        await asyncio.gather(*(tab.on_photo_uploaded(event) for event in events))

    asyncio.run(complete())
    assert len(daily.photos_for_day(0)) == 4
    assert len(daily.photos_for_day(4)) == 2
    assert not tab.pending_uploads and not tab.importing_photos
    assert not list(repo.uploads.glob("*.jpg"))
