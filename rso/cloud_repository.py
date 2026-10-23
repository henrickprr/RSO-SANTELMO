"""Cache local + fila durável + sincronização automática, sem bloquear a digitação."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Event, Lock, Thread
import time
from uuid import uuid4

from .firebase_backend import CloudConflict, friendly_cloud_error, payload_for, revision_for
from .models import Report, ValidationError
from .storage import DraftRepository, atomic_write


class CloudRepository(DraftRepository):
    cloud_enabled = True

    def __init__(self, root: Path | None, backend, *, background: bool = True):
        super().__init__(root)
        self.backend = backend
        self.journal = self.root / "firebase-sync"
        self.journal.mkdir(exist_ok=True)
        self.entries: dict[str, dict] = {}
        self.due: dict[str, float] = {}
        self.first_dirty: dict[str, float] = {}
        self._io_lock = Lock()
        self._wake, self._stop = Event(), Event()
        self._thread = None
        self._background = background
        self._ready = False
        for path in self.journal.glob("*.json"):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                report = Report.from_dict(json.loads(entry["payload"]))
                if path.stem != report.id:
                    raise ValueError("ID divergente")
                if entry["status"] == "syncing":
                    entry["status"] = "pending"
                self.entries[report.id] = entry
                # A fila é gravada antes do JSON de leitura: recuperar uma interrupção
                # entre as duas gravações sem perder o último caractere recebido.
                if entry["status"] != "synced":
                    super().save(report)
                    self.due[report.id] = 0
            except (ValueError, TypeError, KeyError, OSError):
                raise RuntimeError("Fila Firebase ilegível. Preserve a pasta de dados e restaure "
                                   "um backup; a fila original não foi apagada.") from None

    def _write_entry(self, report_id: str, entry: dict):
        atomic_write(self.journal / f"{report_id}.json",
                     json.dumps(entry, ensure_ascii=False).encode("utf-8"))
        self.entries[report_id] = entry

    def save(self, report: Report) -> None:
        payload = payload_for(report)
        revision = revision_for(payload)
        with self.lock:
            existing = self.entries.get(report.id)
            current = revision_for(existing["payload"]) if existing else None
            observed = getattr(report, "_local_revision", None)
            if observed is not None and current != observed:
                raise CloudConflict("Esta aba ficou desatualizada. Use Guardar como cópia "
                                    "para preservar sua edição e reabra o aplicativo.")
            if current == revision:
                report._local_revision = revision
                return
            entry = dict(existing or {"base_revision": None, "media": {}, "saved_at": None})
            entry.update(payload=payload, status="pending", error="")
            self._write_entry(report.id, entry)
            super().save(report)
            report._local_revision = revision
            now = time.monotonic()
            self.first_dirty.setdefault(report.id, now)
            # 1,5 s depois da última edição; digitação contínua envia no máximo a cada 8 s.
            self.due[report.id] = min(now + 1.5, self.first_dirty[report.id] + 8)
        self._wake.set()

    def _target_photo(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.media) or target == self.media:
            raise ValidationError("Caminho de foto Firebase inválido.")
        return target

    def _restore_record(self, report_id: str, record: dict):
        report = Report.from_dict(json.loads(record["payload"]))
        if report.id != report_id or revision_for(record["payload"]) != record["revision"]:
            raise ValidationError("Registro Firebase inválido; cache preservado.")
        for photo in report.photos:
            self._target_photo(photo.path)
            if photo.path not in record.get("media", {}):
                raise ValidationError("O registro Firebase não contém todas as fotos.")
        entry = {"payload": record["payload"], "base_revision": record["revision"],
                 "media": record.get("media", {}), "status": "synced", "error": "",
                 "saved_at": datetime.now(timezone.utc).isoformat()}
        self._write_entry(report_id, entry)
        super().save(report)

    def load_all(self) -> list[Report]:
        # A UI chama este método numa thread e exibe a tela de carregamento.
        # Uma leitura ao abrir, sem polling remoto de cada controle da interface.
        with self._io_lock:
            warnings = []
            try:
                remote = self.backend.list_reports()
            except Exception as exc:
                if not list(self.drafts.glob("*.json")):
                    raise OSError(friendly_cloud_error(exc)) from None
                remote = None
                warnings.append(friendly_cloud_error(exc) + " Exibindo a cópia local disponível.")
            with self.lock:
                if remote is not None:
                    for report_id, record in remote.items():
                        entry = self.entries.get(report_id)
                        local_path = self.drafts / f"{report_id}.json"
                        # Migração: nunca substituir um rascunho local diferente sem avisar.
                        if entry is None and local_path.exists():
                            self.save(self.read(local_path))
                            entry = self.entries.get(report_id)
                        if entry is None or entry["status"] == "synced":
                            self._restore_record(report_id, record)
                        elif revision_for(entry["payload"]) == record["revision"]:
                            self._restore_record(report_id, record)
                        elif entry["base_revision"] != record["revision"]:
                            updated = dict(entry, status="conflict",
                                error=friendly_cloud_error(CloudConflict()))
                            self._write_entry(report_id, updated)
                    # Se o registro remoto sumiu, reenviar somente após compare-and-set.
                    for report_id, entry in list(self.entries.items()):
                        if report_id not in remote and entry["status"] == "synced":
                            self._write_entry(report_id, dict(entry, status="pending", base_revision=None))
                reports = super().load_all()
                warnings.extend(self.warnings)
                for report in reports:
                    if report.id not in self.entries:
                        self.save(report)  # Importação automática dos JSONs anteriores.
                    entry = self.entries[report.id]
                    report._local_revision = revision_for(entry["payload"])
                media = {path: digest for entry in self.entries.values()
                         for path, digest in entry.get("media", {}).items()}
            # Downloads fora do lock de edição; a fila de envio continua serializada.
            for relative, digest in media.items():
                target = self._target_photo(relative)
                if not target.exists():
                    try:
                        self.backend.download_photo(digest, target)
                    except Exception as exc:
                        warnings.append("Não foi possível recuperar uma foto. " + friendly_cloud_error(exc))
                        break  # Evitar repetir dezenas de chamadas durante uma indisponibilidade.
            self.warnings = list(dict.fromkeys(warnings))
            self._ready = True
        self.start()
        return reports

    def start(self):
        if self._background and self._thread is None:
            self._thread = Thread(target=self._worker, name="rso-firebase-sync", daemon=True)
            self._thread.start()

    def ensure_default_reports(self) -> list[Report]:
        with self.lock:
            reports = super().ensure_default_reports()
            for report in reports:
                report._local_revision = revision_for(self.entries[report.id]["payload"])
            return reports

    def request_sync(self, report_id: str):
        with self.lock:
            entry = self.entries.get(report_id)
            if entry and entry["status"] not in ("synced", "conflict"):
                self.due[report_id] = 0
        self._wake.set()

    def sync_status(self, report_id: str) -> dict:
        with self.lock:
            entry = self.entries.get(report_id, {})
            return {key: entry.get(key) for key in ("status", "saved_at", "error")}

    def sync_pending(self, *, force: bool = False):
        if not self._ready:
            return
        with self._io_lock:
            with self.lock:
                ids = [key for key, entry in self.entries.items()
                       if entry["status"] in ("pending", "error")
                       and (force or self.due.get(key, 0) <= time.monotonic())]
            for report_id in ids:
                if self._stop.is_set():
                    return
                self._sync_one(report_id)

    def _sync_one(self, report_id: str):
        with self.lock:
            snapshot = dict(self.entries[report_id])
            self.entries[report_id] = dict(snapshot, status="syncing")
        try:
            report = Report.from_dict(json.loads(snapshot["payload"]))
            media = {}
            for photo in report.photos:
                media[photo.path] = (snapshot["media"].get(photo.path)
                                    or self.backend.upload_photo(self.resolve_photo(photo)))
            revision = self.backend.put_report(snapshot["payload"], media, snapshot["base_revision"])
        except Exception as exc:
            with self.lock:
                entry = dict(self.entries[report_id],
                    status="conflict" if isinstance(exc, CloudConflict) else "error",
                    error=friendly_cloud_error(exc))
                self._write_entry(report_id, entry)
                self.due[report_id] = time.monotonic() + (
                    300 if type(exc).__name__ in {"ResourceExhausted", "TooManyRequests"} else 30)
            return
        with self.lock:
            entry = dict(self.entries[report_id])
            same = revision_for(entry["payload"]) == revision
            entry.update(base_revision=revision, media={**entry["media"], **media},
                status="synced" if same else "pending", error="",
                saved_at=datetime.now(timezone.utc).isoformat())
            self._write_entry(report_id, entry)
            if same:
                self.first_dirty.pop(report_id, None)
                self.due.pop(report_id, None)
            else:
                self.due[report_id] = 0

    def _worker(self):
        while not self._stop.is_set():
            self._wake.wait(timeout=1)
            self._wake.clear()
            try:
                self.sync_pending()
            except OSError:
                # Não encerrar a thread se o cache local ficar temporariamente indisponível.
                self._stop.wait(5)

    def after_restore(self, reports: list[Report]):
        for report in reports:
            self.save(report)
            self.request_sync(report.id)
        self.start()

    def prepare_for_backup(self):
        self.load_all()

    def keep_as_copy(self, report: Report) -> Report:
        copy = Report.from_dict(report.to_dict())
        copy.id = uuid4().hex
        copy.created_at = datetime.now(timezone.utc).isoformat()
        copy.tab_name += " (cópia)"
        self.save(copy)
        self.request_sync(copy.id)
        # A nova fila durável já preserva a edição. Só substituir o original se
        # ele estiver em conflito remoto; uma edição local de outra janela fica intacta.
        with self._io_lock:
            with self.lock:
                conflicted = self.entries.get(report.id, {}).get("status") == "conflict"
            if conflicted:
                try:
                    remote = self.backend.get_report(report.id)
                    if remote:
                        with self.lock:
                            self._restore_record(report.id, remote)
                except Exception:
                    pass  # A cópia está na fila; preservar também o original pendente.
        return copy

    def close(self):
        # O indicador só confirma operações já concluídas. Encerrar não promete
        # salvar uma fila pendente; o journal permite retomá-la em disco persistente.
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._thread is None or not self._thread.is_alive():
            self.backend.close()


def open_repository(root: Path | None = None) -> DraftRepository:
    import os
    mode = os.environ.get("RSO_BACKEND", "local").strip().lower()
    if mode == "local":
        return DraftRepository(root)
    if mode != "firebase":
        raise RuntimeError("RSO_BACKEND deve ser local ou firebase.")
    from .firebase_backend import FirebaseBackend, FirebaseConfig
    return CloudRepository(root, FirebaseBackend(FirebaseConfig.from_env()))
