"""Execute `python main.py` (desktop) ou `python main.py --web` (navegador local)."""

import argparse
import os
from pathlib import Path
import secrets

import flet as ft

from rso.cloud_repository import open_repository
from rso.ui import RSOApp


def main():
    parser = argparse.ArgumentParser(description="Relatórios Semanais de Obra — Santelmo")
    parser.add_argument("--web", action="store_true", help="Abrir no navegador, no próprio computador")
    parser.add_argument("--port", type=int, default=8550)
    parser.add_argument("--data-dir", type=Path, help="Pasta local de rascunhos e fotos")
    args = parser.parse_args()
    repository = open_repository(args.data_dir)
    public = repository.root / "public"
    public.mkdir(exist_ok=True)
    # URLs temporárias de upload no modo web. O modo desktop não depende de servidor externo.
    os.environ.setdefault("FLET_SECRET_KEY", secrets.token_urlsafe(32))

    async def target(page: ft.Page):
        await RSOApp(page, repository).mount()

    try:
        ft.app(target=target, host="127.0.0.1", port=args.port if args.web else 0,
               view=ft.AppView.WEB_BROWSER if args.web else ft.AppView.FLET_APP,
               assets_dir=str(public), upload_dir=str(repository.uploads))
    finally:
        repository.close()


if __name__ == "__main__":
    main()

