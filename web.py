"""Entrada ASGI do Render. Mantém main.py disponível para desktop e uso local.

Executar: python -m uvicorn web:create_app --factory --host 0.0.0.0 --port 10000
Use um único worker: as sessões Flet residem na memória deste processo.
"""

import flet as ft
import flet_web.fastapi as flet_fastapi
from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from rso.backup_web import register_backup_routes
from rso.storage import DraftRepository
from rso.ui import RSOApp
from rso.web_security import AccessMiddleware, WebConfig


def create_app():
    config = WebConfig.from_env()
    repository = DraftRepository(config.data_dir)
    public = repository.root / "public"
    public.mkdir(parents=True, exist_ok=True)

    async def target(page: ft.Page):
        await RSOApp(page, repository).mount()

    # A classe do Flet inicializa/encerra o gerenciador de sessões no lifespan.
    app = flet_fastapi.FastAPI(title="RSO Santelmo", docs_url=None,
                              redoc_url=None, openapi_url=None)
    app.state.repository = repository

    @app.api_route("/healthz", methods=["GET", "HEAD"], include_in_schema=False)
    async def health():
        # Render precisa consultar este endpoint sem conhecer a senha.
        return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})

    @app.put("/upload", include_in_schema=False)
    async def upload(request: Request):
        # Flet 0.28.3 lança exceções genéricas para assinatura/payload inválidos.
        # Convertê-las em respostas 4xx evita tratar erro de upload como queda do servidor.
        try:
            await flet_fastapi.FletUpload(str(repository.uploads),
                max_upload_size=30 * 1024 * 1024, secret_key=config.secret_key).handle(request)
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(400, "URL de upload inválida.") from exc
        except Exception as exc:
            if str(exc) == "Invalid request":
                raise HTTPException(400, "URL de upload inválida ou expirada.") from exc
            if str(exc).startswith("Max upload size reached:"):
                partial = (repository.uploads / request.query_params["f"]).resolve()
                if partial.is_relative_to(repository.uploads):
                    partial.unlink(missing_ok=True)
                raise HTTPException(413, "Cada foto deve ter até 30 MB.") from exc
            raise
        return {"status": "ok"}

    register_backup_routes(app, repository)

    # Registrar saúde e backups ANTES do mount '/', que atende interface e ws.
    app.mount("/", flet_fastapi.app(
        target, assets_dir=str(public), upload_dir=str(repository.uploads),
        max_upload_size=30 * 1024 * 1024, secret_key=config.secret_key,
        app_name="Santelmo • Relatórios de Obra", app_short_name="RSO Santelmo",
        app_description="Relatórios Semanais de Obra", session_timeout_seconds=3600,
    ))
    app.add_middleware(AccessMiddleware, username=config.username, password=config.password)
    return app
