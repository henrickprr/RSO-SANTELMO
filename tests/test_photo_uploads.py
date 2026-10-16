"""Regressões de upload: lista mutável do Flet, stream único e eventos atrasados."""

import asyncio
from types import SimpleNamespace

import flet as ft
from flet.core.file_picker import FilePickerFile
from PIL import Image
import pytest

from rso.models import Report
from rso.storage import DraftRepository
from rso.ui import ObraTab


class Picker:
    def __init__(self, **handlers):
        self.handlers = handlers
        self.batches = []
        self.opened = 0

    def pick_files(self, **kwargs):
        self.opened += 1

    def upload(self, files):
        self.batches.append(files)


class Page:
    web = True

    def __init__(self):
        self.overlay, self.dialogs = [], []

    def update(self):
        pass

    def open(self, dialog):
        self.dialogs.append(dialog)

    def get_upload_url(self, relative, expires):
        return f"/upload/{relative}"


@pytest.fixture
def tab(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "FilePicker", Picker)
    return ObraTab(Page(), Report.new("Casa Sintra"), DraftRepository(tmp_path))


def selection(picker, names):
    return SimpleNamespace(control=picker, files=[
        FilePickerFile(name=name, path=None, size=100, id=i)
        for i, name in enumerate(names)])


async def complete(tab, name, picker=None, error=None):
    if not error:
        path = tab.pending_uploads[name][0]
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (24, 16), "navy").save(path, "JPEG")
    await tab.on_photo_uploaded(SimpleNamespace(
        control=picker or tab.image_picker, file_name=name, progress=1, error=error))


def test_batch_matches_names_when_flet_removes_already_uploaded_files(tab):
    async def run():
        await tab.pick_photos(None)
        event = selection(tab.image_picker, [f"foto-{i}.jpeg" for i in range(8)])
        await tab.on_photos_selected(event)
        remaining = list(event.files)
        # Contrato do cliente Dart 0.28.3: tenta índice primeiro e remove após
        # enviar. A seleção original precisa continuar correta após cada remoção.
        for upload in tab.image_picker.batches[0]:
            file = (remaining[upload.id] if 0 <= upload.id < len(remaining)
                    else next(f for f in remaining if f.name == upload.name))
            assert file.name == upload.name
            remaining.remove(file)
            await complete(tab, file.name)
        assert not remaining and not tab.pending_uploads
        assert [p.original_name for p in tab.report.photos] == [f.name for f in event.files]
        assert not tab.upload_button.disabled
    asyncio.run(run())


def test_duplicate_selection_does_not_read_stream_again_even_after_completion(tab):
    async def run():
        await tab.pick_photos(None)
        event = selection(tab.image_picker, ["QD.jpeg"])
        await tab.on_photos_selected(event)
        await tab.on_photos_selected(event)
        assert tab.importing_photos and tab.upload_button.disabled
        await complete(tab, "QD.jpeg")
        await tab.on_photos_selected(event)
        assert len(tab.image_picker.batches) == 1
        assert len(tab.report.photos) == 1
        assert not tab.pending_uploads and not tab.importing_photos
    asyncio.run(run())


def test_retry_uses_fresh_picker_and_ignores_old_events_for_same_filename(tab):
    async def run():
        await tab.pick_photos(None)
        old = tab.image_picker
        event = selection(old, ["QD.jpeg"])
        await tab.on_photos_selected(event)
        await complete(tab, "QD.jpeg", error="Bad state: Stream has already been listened to.")
        assert not tab.report.photos and not tab.pending_uploads
        assert not tab.upload_button.disabled
        assert "selecione este arquivo novamente" in tab.host_page.dialogs[-1].content.value
        overlay_count = len(tab.host_page.overlay)
        await tab.pick_photos(None)
        current = tab.image_picker
        assert current is not old and old not in tab.host_page.overlay
        assert len(tab.host_page.overlay) == overlay_count
        await tab.on_photos_selected(selection(current, ["QD.jpeg"]))
        await tab.on_photos_selected(event)
        await tab.on_photo_uploaded(SimpleNamespace(
            control=old, file_name="QD.jpeg", progress=1, error="evento antigo"))
        assert "QD.jpeg" in tab.pending_uploads
        assert len(current.batches) == len(old.batches) == 1
        await complete(tab, "QD.jpeg")
        assert len(tab.report.photos) == 1
        assert not tab.pending_uploads and not tab.importing_photos
    asyncio.run(run())


def test_cancel_and_double_click_do_not_leave_button_blocked(tab):
    async def run():
        await tab.pick_photos(None)
        picker = tab.image_picker
        await tab.pick_photos(None)
        assert tab.image_picker is picker and picker.opened == 1
        await tab.on_photos_selected(SimpleNamespace(control=picker, files=None))
        assert not tab.importing_photos and not tab.upload_button.disabled
        await tab.pick_photos(None)
        assert tab.image_picker is not picker
        await tab.on_photos_selected(selection(tab.image_picker, []))
        assert not tab.upload_button.disabled
    asyncio.run(run())


def test_signing_failure_releases_pending_batch(tab, monkeypatch):
    def fail(*args):
        raise ValueError("teste de falha na URL")

    monkeypatch.setattr(tab.host_page, "get_upload_url", fail)

    async def run():
        await tab.pick_photos(None)
        await tab.on_photos_selected(selection(tab.image_picker, ["QD.jpeg"]))
        assert not tab.pending_uploads and not tab.importing_photos
        assert not tab.image_picker.batches
    asyncio.run(run())


def test_uploads_with_same_name_in_different_works_are_isolated(tab):
    other = ObraTab(tab.host_page, Report.new("Casa Bosque"), tab.repository)

    async def run():
        for view in (tab, other):
            await view.pick_photos(None)
            await view.on_photos_selected(selection(view.image_picker, ["QD.jpeg"]))
        assert tab.pending_uploads["QD.jpeg"][0] != other.pending_uploads["QD.jpeg"][0]
        await asyncio.gather(complete(tab, "QD.jpeg"), complete(other, "QD.jpeg"))
        assert len(tab.report.photos) == len(other.report.photos) == 1
        assert tab.report.photos[0].path != other.report.photos[0].path
        assert not tab.pending_uploads and not other.pending_uploads
    asyncio.run(run())


def test_normalization_preserves_completion_order(tab, monkeypatch):
    async def run():
        await tab.pick_photos(None)
        await tab.on_photos_selected(selection(tab.image_picker, ["a.jpeg", "b.jpeg"]))
        started, release = asyncio.Event(), asyncio.Event()
        normalized = []

        async def import_photo(path, name, day):
            if name == "a.jpeg":
                started.set()
                await release.wait()
            normalized.append(name)

        monkeypatch.setattr(tab, "import_photo", import_photo)
        first = asyncio.create_task(complete(tab, "a.jpeg"))
        await started.wait()
        second = asyncio.create_task(complete(tab, "b.jpeg"))
        await asyncio.sleep(0)
        assert not normalized
        release.set()
        await asyncio.gather(first, second)
        assert normalized == ["a.jpeg", "b.jpeg"]
    asyncio.run(run())
