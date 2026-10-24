"""Backup portátil de rascunhos e fotos para o armazenamento temporário do Render Free."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from uuid import uuid4
import zipfile

from PIL import Image

from .models import Report, ValidationError
from .project_state import project_key
from .projects import FIXED_FIELDS, ProjectProfile
from .storage import DraftRepository

MAX_BACKUP_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 200 * 1024 * 1024
MAX_MANIFEST_BYTES = 10 * 1024 * 1024


class BackupService:
    def __init__(self, repository: DraftRepository):
        self.repository = repository

    def create(self, destination: Path) -> Path:
        """Inclui todos os rascunhos atuais e fotos referenciadas, sem validar a exportação.

        Não inclui PDFs/XLSX, versões .bak, fotos já removidas ou credenciais.
        Usa disco e streaming para não duplicar todas as fotos na RAM do plano Free.
        """
        try:
            self.repository.prepare_for_backup()
            with self.repository.lock:
                reports = [self.repository.read_current(p) for p in sorted(self.repository.drafts.glob("*.json"))]
                photos = {p.path: self.repository.resolve_photo(p) for r in reports for p in r.photos}
                manifest = json.dumps({"format": "rso-santelmo", "version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "reports": [r.to_dict() for r in reports]}, ensure_ascii=False).encode()
                if len(manifest) > MAX_MANIFEST_BYTES:
                    raise ValidationError("Os textos dos rascunhos excedem o limite do backup (10 MB).")
                if len(manifest) + sum(p.stat().st_size for p in photos.values()) > MAX_BACKUP_BYTES:
                    raise ValidationError("O backup excede 100 MB. Reduza as fotos antes de continuar.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("backup.json", manifest)
                    for name, path in photos.items():
                        archive.write(path, name)
                if destination.stat().st_size > MAX_BACKUP_BYTES:
                    raise ValidationError("O backup excede 100 MB.")
            return destination
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def restore(self, source: Path) -> list[Report]:
        """Valida antes de publicar. Cria novas obras, preservando as já existentes.

        Nunca usa extractall(): todos os caminhos de destino são gerados pelo app.
        O limite de tamanho descompactado impede consumo descontrolado de disco/RAM.
        """
        if source.stat().st_size > MAX_BACKUP_BYTES:
            raise ValidationError("O backup deve ter até 100 MB.")
        try:
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                names = {info.filename for info in infos}
                if len(infos) > 5000 or len(names) != len(infos):
                    raise ValidationError("Backup com excesso de arquivos ou nomes duplicados.")
                if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
                    raise ValidationError("Backup descompactado excede 200 MB.")
                for info in infos:
                    name = PurePosixPath(info.filename)
                    if (name.is_absolute() or ".." in name.parts or "\\" in info.filename
                            or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1):
                        raise ValidationError("O backup contém caminhos ou arquivos não permitidos.")
                if "backup.json" not in names or archive.getinfo("backup.json").file_size > MAX_MANIFEST_BYTES:
                    raise ValidationError("Selecione um ZIP gerado por Baixar backup neste aplicativo.")
                manifest = json.loads(archive.read("backup.json"))
                if (not isinstance(manifest, dict) or manifest.get("format") != "rso-santelmo"
                        or manifest.get("version") != 1 or not isinstance(manifest.get("reports"), list)):
                    raise ValidationError("Formato de backup não reconhecido.")
                reports = [Report.from_dict(data) for data in manifest["reports"]]
                expected = {"backup.json"}
                for report in reports:
                    for photo in report.photos:
                        parts = PurePosixPath(photo.path).parts
                        if len(parts) < 3 or parts[0] != "media" or photo.path not in names:
                            raise ValidationError("O backup está incompleto: foto ausente ou caminho inválido.")
                        expected.add(photo.path)
                if expected != names:
                    raise ValidationError("O ZIP contém arquivos que não pertencem ao backup.")
                return self._stage_and_publish(archive, reports)
        except (zipfile.BadZipFile, KeyError, TypeError, ValueError, RuntimeError,
                Image.DecompressionBombError) as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError("Não foi possível ler o backup. Verifique se o ZIP está íntegro.") from exc

    def _stage_and_publish(self, archive: zipfile.ZipFile, reports: list[Report]) -> list[Report]:
        with tempfile.TemporaryDirectory(prefix=".rso-restore-", dir=self.repository.root) as temporary:
            staged = DraftRepository(Path(temporary))
            restored_keys = {}
            for report in reports:
                state = self.repository.project_states.get(project_key(report))
                if state and state.deleted:
                    # Restauração explícita cria outra identidade; não remove o marcador
                    # que impede uma sessão antiga de ressuscitar a obra excluída.
                    key = restored_keys.setdefault(state.key, "custom_" + uuid4().hex)
                    profile = report.project_profile
                    if profile is None:
                        values = {name: getattr(report, name) for name in FIXED_FIELDS - {"tab_name"}}
                        profile = ProjectProfile(name=report.tab_name, key=state.key, **values)
                    report.project_profile = replace(profile, key=key, name=profile.name + " (restaurada)")
                    report.project_key = key
                # A correção incompleta continua disponível, mas a referência à revisão
                # de outra instalação não pode autorizar uma sobrescrita do cadastro local.
                current = self.repository.project_states.get(project_key(report))
                report.registration_base = current.revision if current and not current.deleted else ""
                report.id = uuid4().hex
                report.created_at = datetime.now(timezone.utc).isoformat()
                report.tab_name += " (restaurada)"
                copied = {}
                for photo in report.photos:
                    original = photo.path
                    if original not in copied:
                        relative = Path("media") / report.id / f"{uuid4().hex}.jpg"
                        destination = staged.root / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(original) as src, destination.open("wb") as dst:
                            shutil.copyfileobj(src, dst, length=512 * 1024)
                        with Image.open(destination) as image:
                            if image.width * image.height > 16_000_000:
                                raise ValidationError("Foto do backup excede a resolução permitida.")
                            image.verify()
                        copied[original] = relative.as_posix()
                    photo.path = copied[original]
                staged.save(report)
            # Publicar somente depois que todos os JSONs e todas as fotos forem lidos.
            moved_files, moved_dirs = [], []
            with self.repository.lock:
                try:
                    for report in reports:
                        source_media = staged.media / report.id
                        if source_media.exists():
                            target_media = self.repository.media / report.id
                            os.replace(source_media, target_media)
                            moved_dirs.append(target_media)
                        target = self.repository.drafts / f"{report.id}.json"
                        os.replace(staged.drafts / target.name, target)
                        moved_files.append(target)
                except OSError:
                    for path in moved_files:
                        path.unlink(missing_ok=True)
                    for path in moved_dirs:
                        shutil.rmtree(path)
                    raise
            self.repository.after_restore(reports)
            return reports
