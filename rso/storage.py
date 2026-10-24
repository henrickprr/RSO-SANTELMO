"""Persistência offline: um JSON por relatório, gravação atômica e cópia anterior."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from threading import RLock
from uuid import UUID, uuid4

from PIL import Image, ImageOps
from platformdirs import user_data_path

from .models import Photo, Report, ValidationError
from .project_state import ProjectChanged, ProjectDeleted, ProjectState, project_key
from .projects import apply_project


def default_data_dir() -> Path:
    return Path(os.environ.get("RSO_DATA_DIR") or user_data_path("RSO-Santelmo", appauthor=False))


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".rso-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class DraftRepository:
    cloud_enabled = False

    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_data_dir()).resolve()
        self.drafts = self.root / "drafts"
        self.media = self.root / "media"
        self.uploads = self.root / "uploads"
        self.exports = self.root / "exports"
        for directory in (self.drafts, self.media, self.uploads, self.exports):
            directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.warnings: list[str] = []
        self.project_file = self.root / "project-state.json"
        self.project_states = {}
        if self.project_file.exists():
            for key, value in json.loads(self.project_file.read_text(encoding="utf-8")).items():
                state = ProjectState.from_dict(value)
                if key != state.key:
                    raise ValueError("Cadastro local inconsistente; preserve a pasta de dados.")
                self.project_states[key] = state

    def apply_registration(self, report: Report) -> None:
        state = self.project_states.get(project_key(report))
        if state:
            if state.deleted:
                raise ProjectDeleted()
            report.project_key = state.key
            report.project_profile = state.profile
            report.tab_name = state.profile.name
        apply_project(report)

    def read_current(self, path: Path) -> Report:
        report = self.read(path)
        self.apply_registration(report)
        return report

    def _write_project_states(self, states) -> None:
        atomic_write(self.project_file, json.dumps({k: v.to_dict() for k, v in states.items()},
                                                  ensure_ascii=False).encode())
        self.project_states = states

    def set_project_state(self, state: ProjectState, expected: str | None) -> None:
        with self.lock:
            current = self.project_states.get(state.key)
            if current and current.deleted and not state.deleted:
                raise ProjectDeleted()
            if (current.revision if current else None) != expected:
                if current == state:  # Repetição após confirmação perdida.
                    if state.deleted:
                        self._purge_deleted()
                    return
                raise ProjectChanged()
            self._write_project_states({**self.project_states, state.key: state})
            if state.deleted:
                self._purge_deleted()

    def _purge_deleted(self) -> set[str]:
        """Remover somente fotos sem referência em qualquer outro relatório local."""
        removed, candidates, keep = set(), set(), set()
        for path in self.drafts.glob("*.json"):
            try:
                report = self.read(path)
            except (OSError, ValueError, TypeError, KeyError):
                # Um arquivo ilegível pode referenciar fotos; não fazer limpeza de mídia.
                keep = None
                continue
            state = self.project_states.get(project_key(report))
            if state and state.deleted:
                removed.add(report.id)
                candidates.update(p.path for p in report.photos)
                path.unlink(missing_ok=True)
                path.with_suffix(".json.bak").unlink(missing_ok=True)
            elif keep is not None:
                keep.update(p.path for p in report.photos)
        for relative in candidates - keep if keep is not None else ():
            target = (self.root / relative).resolve()
            if target.is_relative_to(self.media):
                target.unlink(missing_ok=True)
        return removed

    def after_restore(self, reports: list[Report]) -> None:
        """Gancho para a fila de sincronização; o armazenamento local já foi gravado."""

    def prepare_for_backup(self) -> None:
        """O backend remoto recupera os arquivos antes de produzir o ZIP."""

    def close(self) -> None:
        """O backend remoto encerra seu worker; o local não possui recursos abertos."""

    def ensure_default_reports(self) -> list[Report]:
        with self.lock:
            # Duas sessões podem abrir simultaneamente uma instalação vazia.
            reports = [self.read_current(path) for path in sorted(self.drafts.glob("*.json"))]
            if not reports and not self.project_states:
                for name, template in (("Casa Bella Vista", "wide"), ("Casa Bosque", "compact"),
                                       ("Casa Sintra", "sintra"), ("Casa Átrio", "compact")):
                    report = Report.new(name, template)
                    self.save(report)
                    reports.append(report)
            return reports

    def save(self, report: Report) -> None:
        # Não validar inputs durante digitação: '02/' também precisa sobreviver a uma queda.
        UUID(report.id)
        path = self.drafts / f"{report.id}.json"
        with self.lock:
            self.apply_registration(report)
            payload = json.dumps({"schema_version": 2, "report": report.to_dict()},
                                 ensure_ascii=False, indent=2).encode("utf-8")
            if path.exists():
                atomic_write(path.with_suffix(".json.bak"), path.read_bytes())
            atomic_write(path, payload)

    @staticmethod
    def read(path: Path) -> Report:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") not in (1, 2):
            raise ValidationError("Versão de rascunho não suportada.")
        return Report.from_dict(data["report"])

    def load_all(self) -> list[Report]:
        reports = []
        self.warnings = []
        for path in sorted(self.drafts.glob("*.json")):
            try:
                report = self.read_current(path)
                if report.id != path.stem:
                    raise ValidationError("Identificador divergente do nome do arquivo.")
            except ProjectDeleted:
                continue
            except (ValueError, TypeError, KeyError, OSError) as exc:
                # Preservar o arquivo com falha para recuperação manual, sem apagá-lo.
                damaged = path.with_suffix(f".corrupt-{uuid4().hex[:8]}")
                try:
                    report = self.read_current(path.with_suffix(".json.bak"))
                    if report.id != path.stem:
                        raise ValidationError("Backup de outra obra.")
                except (ValueError, TypeError, KeyError, OSError):
                    self.warnings.append(f"Não foi possível ler {path.name}: {exc}")
                    continue
                shutil.copy2(path, damaged)
                atomic_write(path, path.with_suffix(".json.bak").read_bytes())
                self.warnings.append(f"{report.tab_name}: cópia anterior recuperada; original em {damaged.name}.")
            reports.append(report)
        return sorted(reports, key=lambda report: (report.created_at, report.id))

    def resolve_photo(self, photo: Photo) -> Path:
        # Referências internas continuam válidas ao mover/copiar toda a pasta de dados.
        path = (self.root / photo.path).resolve()
        if not path.is_relative_to(self.media):
            raise ValidationError(f"Caminho de foto inválido: {photo.original_name or photo.id}")
        if not path.is_file():
            raise ValidationError(f"Foto ausente: {photo.original_name or photo.id}. Reimporte a imagem.")
        return path

    def import_photo(self, source: Path, report_id: str) -> Photo:
        UUID(report_id)
        if source.stat().st_size > 30 * 1024 * 1024:
            raise ValidationError("Cada foto deve ter até 30 MB.")
        try:
            with Image.open(source) as opened:
                opened.load()
                image = ImageOps.exif_transpose(opened)
                # Celulares: normalizar EXIF e transparência antes de PDF/Excel.
                canvas = Image.new("RGB", image.size, "white")
                if "A" in image.getbands():
                    canvas.paste(image, mask=image.getchannel("A"))
                else:
                    canvas.paste(image.convert("RGB"))
                canvas.thumbnail((2800, 2800), Image.Resampling.LANCZOS)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValidationError("Imagem inválida. Use JPG, PNG ou WebP.") from exc
        photo_id = uuid4().hex
        relative = Path("media") / report_id / f"{photo_id}.jpg"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target, "JPEG", quality=92, optimize=True)
        return Photo(id=photo_id, path=relative.as_posix(), original_name=source.name)

