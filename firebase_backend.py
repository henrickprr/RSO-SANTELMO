"""Firebase Spark: Firestore para rascunhos e fotos, sem Cloud Storage/Blaze.

Fotos JPEG são imutáveis e endereçadas por SHA-256. Cada parte fica abaixo do
limite de 1 MiB por documento; o manifesto só é publicado depois de todas as
partes. Um relatório só é confirmado depois das fotos. Nunca usa URLs públicas.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import UUID, uuid4

from .models import Report, ValidationError
from .project_state import ProjectChanged, ProjectDeleted, ProjectState, project_key

CHUNK_BYTES = 700 * 1024
MAX_PHOTO_BYTES = 30 * 1024 * 1024
MAX_REPORT_BYTES = 800 * 1024


class CloudConflict(OSError):
    pass


def payload_for(report: Report) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def revision_for(payload: str) -> str:
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FirebaseConfig:
    project_id: str
    namespace: str = "santelmo"
    database_id: str = "(default)"

    @classmethod
    def from_env(cls):
        project = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
        namespace = os.environ.get("RSO_FIREBASE_NAMESPACE", "santelmo").strip()
        database = os.environ.get("FIREBASE_DATABASE_ID", "(default)").strip()
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project):
            raise RuntimeError("Configure FIREBASE_PROJECT_ID com o ID do projeto Firebase.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", namespace):
            raise RuntimeError("RSO_FIREBASE_NAMESPACE deve conter apenas letras, números, _ ou -.")
        if database != "(default)":
            raise RuntimeError("Use o banco (default), que pode utilizar a cota gratuita do Firestore.")
        return cls(project, namespace, database)


class FirebaseBackend:
    def __init__(self, config: FirebaseConfig, *, client=None):
        self.config = config
        self._app = None
        if client is None:
            import firebase_admin
            from firebase_admin import credentials, firestore

            try:
                raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
                if raw:
                    info = json.loads(raw)
                    if info.get("project_id") != config.project_id:
                        raise ValueError("Projeto divergente")
                    credential = credentials.Certificate(info)
                else:
                    # GOOGLE_APPLICATION_CREDENTIALS aponta para um Secret File do Render.
                    credential = credentials.ApplicationDefault()
                self._app = firebase_admin.initialize_app(credential,
                    {"projectId": config.project_id}, name=f"rso-{uuid4().hex}")
                client = firestore.client(self._app, database_id=config.database_id)
            except Exception:
                # Exceções de credenciais podem conter trechos privados. Não propagá-las.
                raise RuntimeError("Credencial Firebase inválida ou ausente. Configure o Secret File "
                                   "GOOGLE_APPLICATION_CREDENTIALS conforme FIREBASE.md.") from None
        self.client = client
        space = client.collection("rso_workspaces").document(config.namespace)
        self.reports = space.collection("reports")
        self.photos = space.collection("photos")
        self.projects = space.collection("projects")
        self._known_photos: set[str] = set()

    def list_projects(self) -> dict[str, ProjectState]:
        states = {}
        for document in self.projects.stream(timeout=15, retry=None):
            state = ProjectState.from_dict(document.to_dict())
            if state.key != document.id:
                raise ValidationError("Cadastro Firebase inconsistente.")
            states[state.key] = state
        return states

    def put_project(self, state: ProjectState, expected: str | None) -> None:
        from google.cloud import firestore
        reference = self.projects.document(state.key)

        @firestore.transactional
        def store(transaction):
            snapshot = reference.get(transaction=transaction, timeout=15, retry=None)
            current = snapshot.to_dict() or {}
            if current.get("revision") == state.revision:
                return
            if current.get("deleted"):
                raise ProjectDeleted()
            if current.get("revision") != expected:
                raise ProjectChanged()
            transaction.set(reference, state.to_dict())
        store(self.client.transaction(max_attempts=3))

    def purge_reports(self, ids: list[str]) -> None:
        # Só os documentos já identificados como pertencentes às obras excluídas.
        # Fotos por hash podem ser compartilhadas: não remover seus blocos aqui.
        for start in range(0, len(ids), 200):
            batch = self.client.batch()
            for report_id in ids[start:start + 200]:
                UUID(report_id)
                batch.delete(self.reports.document(report_id))
            batch.commit(timeout=15, retry=None)

    def list_reports(self) -> dict[str, dict]:
        result = {}
        for document in self.reports.stream(timeout=15, retry=None):
            UUID(document.id)
            value = document.to_dict()
            report = Report.from_dict(json.loads(value["payload"]))
            if report.id != document.id or revision_for(value["payload"]) != value["revision"]:
                raise ValidationError("Relatório Firebase inconsistente; a cópia local foi preservada.")
            result[document.id] = value
        return result

    def get_report(self, report_id: str) -> dict | None:
        UUID(report_id)
        document = self.reports.document(report_id).get(timeout=15, retry=None)
        return document.to_dict() if document.exists else None

    def upload_photo(self, path: Path) -> str:
        # Nunca subir o original não normalizado recebido do navegador.
        size = path.stat().st_size
        if not 0 < size <= MAX_PHOTO_BYTES:
            raise ValidationError("Foto fora do limite permitido para sincronização (30 MB).")
        digest = sha256(path.read_bytes()).hexdigest()
        if digest in self._known_photos:
            return digest
        manifest = self.photos.document(digest)
        current = manifest.get(timeout=15, retry=None)
        if not current.exists:
            # Lotes pequenos: o Firestore também limita cada requisição a 10 MiB.
            count = 0
            with path.open("rb") as source:
                while chunk := source.read(CHUNK_BYTES):
                    manifest.collection("chunks").document(f"{count:04d}").set(
                        {"data": chunk}, timeout=15, retry=None)
                    count += 1
            manifest.set({"sha256": digest, "size": size, "chunks": count,
                          "content_type": "image/jpeg"}, timeout=15, retry=None)
        else:
            metadata = current.to_dict()
            if (metadata.get("size") != size or metadata.get("sha256") != digest
                    or metadata.get("chunks") != (size + CHUNK_BYTES - 1) // CHUNK_BYTES):
                raise ValidationError("A foto salva no Firebase está inconsistente.")
        self._known_photos.add(digest)
        return digest

    def download_photo(self, digest: str, target: Path) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValidationError("Referência de foto Firebase inválida.")
        manifest = self.photos.document(digest)
        metadata = manifest.get(timeout=15, retry=None).to_dict()
        if (not metadata or metadata.get("sha256") != digest
                or type(metadata.get("size")) is not int
                or not 0 < metadata["size"] <= MAX_PHOTO_BYTES
                or metadata.get("chunks") != (metadata["size"] + CHUNK_BYTES - 1) // CHUNK_BYTES):
            raise ValidationError("Foto incompleta no Firebase; reenvie a imagem original.")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".firebase-", dir=target.parent)
        checksum, total = sha256(), 0
        try:
            with os.fdopen(fd, "wb") as output:
                for index in range(metadata["chunks"]):
                    part = manifest.collection("chunks").document(f"{index:04d}").get(
                        timeout=15, retry=None).to_dict()
                    data = part.get("data") if part else None
                    if not isinstance(data, bytes) or not 0 < len(data) <= CHUNK_BYTES:
                        raise ValidationError("Parte de uma foto ausente no Firebase.")
                    checksum.update(data)
                    total += len(data)
                    output.write(data)
                output.flush()
                os.fsync(output.fileno())
            if total != metadata["size"] or checksum.hexdigest() != digest:
                raise ValidationError("Falha na verificação de integridade da foto.")
            os.replace(temporary, target)
            self._known_photos.add(digest)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def put_report(self, payload: str, media: dict[str, str], expected: str | None) -> str:
        from google.cloud import firestore

        if len(payload.encode("utf-8")) + len(json.dumps(media).encode()) > MAX_REPORT_BYTES:
            raise ValidationError("Os textos deste relatório excedem o limite do Firebase (800 KB).")
        report = Report.from_dict(json.loads(payload))
        report_id = report.id
        UUID(report_id)
        revision = revision_for(payload)
        reference = self.reports.document(report_id)

        @firestore.transactional
        def store(transaction):
            state = self.projects.document(project_key(report)).get(
                transaction=transaction, timeout=15, retry=None).to_dict()
            if state and state.get("deleted"):
                raise ProjectDeleted()
            current = reference.get(transaction=transaction, timeout=15, retry=None)
            existing = current.to_dict() if current.exists else {}
            if existing.get("revision") == revision:
                return  # Confirmação perdida na rede: repetir não duplica a alteração.
            if existing.get("revision") != expected:
                raise CloudConflict("Este relatório foi atualizado em outra sessão.")
            transaction.set(reference, {"schema_version": 2, "payload": payload,
                "revision": revision, "media": media, "updated_at": firestore.SERVER_TIMESTAMP})

        store(self.client.transaction(max_attempts=3))
        return revision

    def close(self):
        self.client.close()
        if self._app is not None:
            import firebase_admin
            firebase_admin.delete_app(self._app)


def friendly_cloud_error(error: Exception) -> str:
    """Mensagens úteis sem vazar resposta da API, chave ou conteúdo do relatório."""
    code = type(error).__name__
    if code in {"ResourceExhausted", "TooManyRequests"}:
        return "Cota gratuita do Firebase atingida. Salvamento pendente; baixe um backup."
    if code in {"PermissionDenied", "Unauthenticated", "DefaultCredentialsError", "RefreshError"}:
        return "Firebase sem acesso. Revise a credencial e as permissões no Render."
    if code in {"NotFound", "FailedPrecondition"}:
        return "Confira se o banco Firestore (default) foi criado no projeto configurado."
    if isinstance(error, CloudConflict):
        return "Outra sessão alterou este relatório. Preserve sua edição como uma cópia."
    if isinstance(error, (ProjectChanged, ProjectDeleted)):
        return str(error)
    if isinstance(error, ValidationError):
        return str(error)
    return "Firebase indisponível. Salvamento pendente; uma nova tentativa será feita."
