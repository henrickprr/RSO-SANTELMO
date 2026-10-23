"""Contrato real do SDK com emulador oficial. Nunca acessa um projeto de produção."""

from hashlib import sha256
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
