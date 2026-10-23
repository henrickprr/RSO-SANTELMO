"""Rotas autenticadas de backup; não dependem de Shell nem disco pago do Render."""

import asyncio
from datetime import datetime
from pathlib import Path
import tempfile

from fastapi import FastAPI, HTTPException, Request
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, HTMLResponse

from .backup import BackupService, MAX_BACKUP_BYTES
from .models import ValidationError
from .settings import ASSETS
from .storage import DraftRepository


def register_backup_routes(app: FastAPI, repository: DraftRepository) -> None:
    service = BackupService(repository)

    @app.get("/backup", include_in_schema=False)
    async def backup_page():
        notice = ("Com Firebase ativo, aguarde Salvo no Firebase antes de fechar. Este ZIP "
                  "é uma cópia independente dos seus dados. Pendências ainda não sincronizadas "
                  "podem se perder se o Render apagar o cache local."
                  if repository.cloud_enabled else
                  "No Render Free, os dados locais são temporários. Baixe um backup antes de "
                  "sair, reiniciar ou atualizar o aplicativo. Sem ele, alterações perdidas "
                  "pelo servidor não podem ser recuperadas.")
        return HTMLResponse((ASSETS / "backup.html").read_text(encoding="utf-8").replace(
            "{{STORAGE_NOTICE}}", notice))

    @app.get("/backup/download", include_in_schema=False)
    async def download():
        with tempfile.NamedTemporaryFile(suffix=".zip", dir=repository.uploads, delete=False) as tmp:
            path = Path(tmp.name)
        try:
            await asyncio.to_thread(service.create, path)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(400, "Não foi possível criar o backup. " + str(exc)) from exc
        return FileResponse(path, media_type="application/zip",
            filename=f"RSO-Backup-{datetime.now():%Y%m%d-%H%M%S}.zip",
            background=BackgroundTask(path.unlink, missing_ok=True))

    @app.post("/backup/restore", include_in_schema=False)
    async def restore(request: Request):
        # Recebe o ZIP em streaming; não carrega o corpo inteiro na memória do Free.
        with tempfile.NamedTemporaryFile(suffix=".zip", dir=repository.uploads, delete=False) as tmp:
            path = Path(tmp.name)
        try:
            size = 0
            with path.open("wb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BACKUP_BYTES:
                        raise HTTPException(413, "O backup deve ter até 100 MB.")
                    await asyncio.to_thread(stream.write, chunk)
            reports = await asyncio.to_thread(service.restore, path)
            return {"restored": len(reports), "detail":
                f"{len(reports)} obra(s) restaurada(s). Recarregue a janela do aplicativo para continuar."}
        except (ValidationError, OSError) as exc:
            raise HTTPException(400, "Não foi possível restaurar o backup. " + str(exc)) from exc
        finally:
            path.unlink(missing_ok=True)
