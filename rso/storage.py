"""Persistência offline: um JSON por obra, gravação atômica e cópia anterior."""

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

    def save(self, report: Report) -> None:
        # Não validar inputs durante digitação: '02/' também precisa sobreviver a uma queda.
        UUID(report.id)
        path = self.drafts / f"{report.id}.json"
        payload = json.dumps({"schema_version": 2, "report": report.to_dict()},
                             ensure_ascii=False, indent=2).encode("utf-8")
        with self.lock:
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
                report = self.read(path)
                if report.id != path.stem:
                    raise ValidationError("Identificador divergente do nome do arquivo.")
            except (ValueError, TypeError, KeyError, OSError) as exc:
                # Preservar o arquivo com falha para recuperação manual, sem apagá-lo.
                damaged = path.with_suffix(f".corrupt-{uuid4().hex[:8]}")
                try:
                    report = self.read(path.with_suffix(".json.bak"))
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

