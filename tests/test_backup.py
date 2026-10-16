"""Backups precisam sobreviver à perda do diretório temporário sem danificar outras obras."""

from io import BytesIO
import json
import stat
import zipfile

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from rso.backup import BackupService
from rso.models import Report, ValidationError
from rso.storage import DraftRepository
from web import create_app


@pytest.fixture
def data(tmp_path):
    repository = DraftRepository(tmp_path / "source")
    report = Report.new("Casa backup")
    report.start = "02/"  # Rascunho incompleto também precisa de backup.
    report.activities[0] = "Atividade com acentuação preservada"
    report.holidays = True
    report.holiday_description = "12/10 — Nossa Senhora Aparecida"
    source = tmp_path / "image.jpg"
    Image.new("RGB", (100, 160), "navy").save(source)
    photo = repository.import_photo(source, report.id)
    photo.caption = "Legenda preservada"
    report.add_photo(photo, 1)  # Uma foto é válida para backup, mesmo impedindo exportação.
    repository.save(report)
    return repository, report


def test_restore_after_losing_all_server_files_preserves_draft_and_photo(data, tmp_path):
    repository, original = data
    archive = BackupService(repository).create(tmp_path / "backup.zip")
    destination = DraftRepository(tmp_path / "new-server")
    restored = BackupService(destination).restore(archive)
    assert len(restored) == 1
    new = restored[0]
    assert new.id != original.id
    assert new.tab_name == "Casa backup (restaurada)"
    assert new.start == "02/" and new.activities == original.activities
    assert new.holidays and new.holiday_description == original.holiday_description
    assert new.photos[0].day == 1 and new.photos[0].caption == "Legenda preservada"
    assert destination.resolve_photo(new.photos[0]).read_bytes() == repository.resolve_photo(original.photos[0]).read_bytes()
    assert DraftRepository(destination.root).load_all()[0].photos[0].caption == "Legenda preservada"


def test_restore_never_overwrites_existing_work_and_excludes_unreferenced_files(data, tmp_path):
    repo, original = data
    (repo.exports / "old.pdf").write_bytes(b"pdf")
    (repo.media / "removed.jpg").write_bytes(b"removed")
    path = BackupService(repo).create(tmp_path / "backup.zip")
    with zipfile.ZipFile(path) as z:
        assert set(z.namelist()) == {"backup.json", original.photos[0].path}
    restored = BackupService(repo).restore(path)
    assert restored[0].id != original.id
    reports = {r.id: r for r in repo.load_all()}
    assert len(reports) == 2
    assert reports[original.id].to_dict() == original.to_dict()


def test_missing_photo_prevents_incomplete_backup(data, tmp_path):
    repo, original = data
    repo.resolve_photo(original.photos[0]).unlink()
    path = tmp_path / "backup.zip"
    with pytest.raises(ValidationError, match="Foto ausente"):
        BackupService(repo).create(path)
    assert not path.exists()


@pytest.mark.parametrize("dangerous", ["../outside.txt", "/absolute.txt", "media\\outside.txt"])
def test_path_traversal_archive_never_writes_files(data, tmp_path, dangerous):
    repo, _ = data
    path = tmp_path / "invalid.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(dangerous, b"outside")
    before = list(repo.drafts.iterdir())
    with pytest.raises(ValidationError):
        BackupService(repo).restore(path)
    assert list(repo.drafts.iterdir()) == before
    assert not (tmp_path / "outside.txt").exists()


def test_symlink_archive_rejected(data, tmp_path):
    repo, _ = data
    path = tmp_path / "link.zip"
    info = zipfile.ZipInfo("link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(info, "../outside")
    with pytest.raises(ValidationError):
        BackupService(repo).restore(path)


def test_invalid_late_photo_leaves_no_partially_restored_reports(data, tmp_path):
    repo, original = data
    first = original.to_dict()
    second = original.to_dict()
    second["photos"][0]["path"] = "media/other/corrupt.jpg"
    path = tmp_path / "corrupt-photo.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("backup.json", json.dumps({"format": "rso-santelmo", "version": 1,
                                               "reports": [first, second]}))
        z.write(repo.resolve_photo(original.photos[0]), original.photos[0].path)
        z.writestr("media/other/corrupt.jpg", b"not-an-image")
    destination = DraftRepository(tmp_path / "destination")
    with pytest.raises((OSError, ValidationError)):
        BackupService(destination).restore(path)
    assert destination.load_all() == []
    assert not list(destination.media.iterdir())
    assert not list(destination.root.glob(".rso-restore-*"))


def test_compressed_bomb_is_rejected_before_reading_contents(data, tmp_path, monkeypatch):
    repo, _ = data
    monkeypatch.setattr("rso.backup.MAX_EXPANDED_BYTES", 1024)
    path = tmp_path / "large.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("backup.json", b"x" * 1025)
    with pytest.raises(ValidationError, match="descompactado"):
        BackupService(repo).restore(path)


@pytest.fixture
def web(data, monkeypatch):
    repo, _ = data
    monkeypatch.setenv("RSO_USERNAME", "teste")
    monkeypatch.setenv("RSO_PASSWORD", "senha-teste-2026")
    monkeypatch.setenv("FLET_SECRET_KEY", "chave-teste-com-mais-de-32-caracteres")
    monkeypatch.setenv("RSO_DATA_DIR", str(repo.root))
    monkeypatch.setenv("RSO_STORAGE_MODE", "ephemeral")
    return TestClient(create_app())


AUTH = ("teste", "senha-teste-2026")


def test_backup_routes_require_authentication_and_prevent_cross_origin_restore(web):
    assert web.get("/backup").status_code == 401
    assert web.get("/backup/download").status_code == 401
    assert web.post("/backup/restore", content=b"zip").status_code == 401
    assert web.post("/backup/restore", content=b"zip", auth=AUTH,
                    headers={"Origin": "https://outro.invalid"}).status_code == 403


def test_web_download_and_restore_round_trip_with_temporary_file_cleanup(web, data):
    repo, _ = data
    response = web.get("/backup/download", auth=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "no-store" in response.headers["cache-control"]
    assert not list(repo.uploads.iterdir())
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert "backup.json" in archive.namelist()
    restored = web.post("/backup/restore", auth=AUTH, content=response.content)
    assert restored.status_code == 200
    assert restored.json()["restored"] == 1
    assert len(repo.load_all()) == 2
    assert not list(repo.uploads.iterdir())


def test_bad_backup_returns_readable_error_without_changing_drafts(web, data):
    repo, _ = data
    result = web.post("/backup/restore", auth=AUTH, content=b"not-zip")
    assert result.status_code == 400
    assert "backup" in result.json()["detail"]
    assert len(repo.load_all()) == 1
    assert not list(repo.uploads.iterdir())


def test_streamed_upload_size_limit_removes_partial_file(web, data, monkeypatch):
    repo, _ = data
    monkeypatch.setattr("rso.backup_web.MAX_BACKUP_BYTES", 10)
    response = web.post("/backup/restore", auth=AUTH, content=b"x" * 11)
    assert response.status_code == 413
    assert not list(repo.uploads.iterdir())
