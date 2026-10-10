"""Protege HTTP, uploads, downloads e WebSockets com a mesma credencial.

O navegador apresenta seu diálogo nativo de usuário/senha (HTTP Basic). No Render,
a conexão externa é HTTPS. Este controle é de acesso a uma instalação privada;
não implementa cadastro de usuários nem permissões por obra.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hmac
import os
from pathlib import Path
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .storage import default_data_dir


@dataclass(frozen=True)
class WebConfig:
    username: str
    password: str
    secret_key: str
    data_dir: Path

    @classmethod
    def from_env(cls) -> WebConfig:
        names = ("RSO_USERNAME", "RSO_PASSWORD", "FLET_SECRET_KEY")
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise RuntimeError("Configure as variáveis do servidor: " + ", ".join(missing))
        username, password, secret = (os.environ[name] for name in names)
        if not username.isascii() or not username.isprintable() or ":" in username:
            raise RuntimeError("RSO_USERNAME deve usar caracteres ASCII, sem dois-pontos.")
        if len(password) < 12:
            raise RuntimeError("RSO_PASSWORD deve ter pelo menos 12 caracteres.")
        if len(secret) < 32:
            raise RuntimeError("FLET_SECRET_KEY deve ter pelo menos 32 caracteres.")
        if os.environ.get("RENDER") == "true" and not os.environ.get("RSO_DATA_DIR"):
            raise RuntimeError("Configure RSO_DATA_DIR; no Render Free use /tmp/rso-data.")
        return cls(username, password, secret, default_data_dir())


class AccessMiddleware:
    def __init__(self, app: ASGIApp, username: str, password: str):
        self.app = app
        self.username = username.encode("utf-8")
        self.password = password.encode("utf-8")

    def authorized(self, header: str) -> bool:
        try:
            scheme, credentials = header.split(" ", 1)
            if scheme.lower() != "basic":
                return False
            user, password = base64.b64decode(credentials, validate=True).split(b":", 1)
        except (ValueError, binascii.Error):
            return False
        # Comparar ambos os valores, sem expor senhas em mensagens ou logs.
        user_ok = hmac.compare_digest(user, self.username)
        password_ok = hmac.compare_digest(password, self.password)
        return user_ok & password_ok

    @staticmethod
    def same_origin(headers: Headers) -> bool:
        origin = headers.get("origin")
        if origin is None:
            return True  # Clientes não-browser ainda precisam apresentar a senha.
        try:
            parsed = urlsplit(origin)
            return (parsed.scheme in ("http", "https")
                    and parsed.netloc.lower() == headers.get("host", "").lower())
        except ValueError:
            return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        is_health = (scope["type"] == "http" and scope["path"] == "/healthz"
                     and scope["method"] in ("GET", "HEAD"))
        headers = Headers(scope=scope)
        if not is_health and not self.authorized(headers.get("authorization", "")):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                response = JSONResponse({"detail": "Informe usuário e senha para acessar o RSO."},
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="RSO Santelmo", charset="UTF-8"',
                             "Cache-Control": "no-store"})
                await response(scope, receive, send)
            return
        # Impedir que páginas de outra origem usem credenciais já memorizadas pelo browser.
        writes = scope["type"] == "websocket" or scope.get("method") not in ("GET", "HEAD", "OPTIONS")
        if not is_health and writes and not self.same_origin(headers):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse({"detail": "Origem não permitida."}, status_code=403)(
                    scope, receive, send)
            return

        async def secured_send(message):
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"),
                         (b"x-frame-options", b"DENY"),
                         (b"referrer-policy", b"same-origin")]
                if scope["path"].startswith(("/downloads/", "/backup")):
                    # Relatórios não devem permanecer no cache de proxies compartilhados.
                    message["headers"] = [(k, v) for k, v in message.get("headers", [])
                                          if k.lower() != b"cache-control"]
                    extra.append((b"cache-control", b"private, no-store"))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, secured_send)
