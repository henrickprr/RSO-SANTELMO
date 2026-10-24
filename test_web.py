"""Verifica limites reais da publicação: autenticação, uploads e dados persistentes."""

import base64
from pathlib import Path

from fastapi.testclient import TestClient
from flet_web.uploads import build_upload_url
import pytest
from starlette.websockets import WebSocketDisconnect
import yaml

from rso.models import Report
from rso.storage import DraftRepository
from rso.web_security import WebConfig
from web import create_app

AUTH = ("teste", "senha-teste-2026")
SECRET = "chave-exclusiva-dos-testes-com-32-caracteres"


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("RSO_USERNAME", AUTH[0])
    monkeypatch.setenv("RSO_PASSWORD", AUTH[1])
    monkeypatch.setenv("FLET_SECRET_KEY", SECRET)
    monkeypatch.setenv("RSO_DATA_DIR", str(tmp_path / "persistente"))
    monkeypatch.delenv("RENDER", raising=False)
    return tmp_path / "persistente"


@pytest.fixture
def app(environment):
    return create_app()


@pytest.fixture
def client(app):
    # A fábrica precisa ser testável sem iniciar um servidor nem uma janela desktop.
    return TestClient(app)


def test_health_is_public_and_does_not_disclose_data(client):
    result = client.get("/healthz")
    assert result.status_code == 200
    assert result.json() == {"status": "ok"}
    assert client.head("/healthz").status_code == 200


@pytest.mark.parametrize("path", ["/", "/main.dart.js", "/downloads/falso/rso.pdf",
                                   "/drafts/falso.json", "/healthz/outra-rota"])
def test_private_routes_require_password(client, path):
    result = client.get(path)
    assert result.status_code == 401
    assert result.headers["www-authenticate"].startswith("Basic ")


@pytest.mark.parametrize("authorization", ["Basic ???", "Bearer token", "Basic YTo=", "Basic"])
def test_malformed_authorization_never_crashes(client, authorization):
    assert client.get("/", headers={"Authorization": authorization}).status_code == 401


def test_wrong_credentials_are_rejected(client):
    assert client.get("/", auth=(AUTH[0], "incorreta")).status_code == 401
    assert client.get("/", auth=("outro", AUTH[1])).status_code == 401


def test_authenticated_app_and_static_assets(client):
    page = client.get("/", auth=AUTH)
    assert page.status_code == 200
    assert "flutter" in page.text.lower()
    assert client.get("/flutter_bootstrap.js", auth=AUTH).status_code == 200


def test_download_is_protected_and_never_publicly_cached(client, environment):
    target = environment / "public" / "downloads" / "test" / "rso.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-teste-de-download")
    assert client.get("/downloads/test/rso.pdf").status_code == 401
    result = client.get("/downloads/test/rso.pdf", auth=AUTH)
    assert result.status_code == 200
    assert result.content == target.read_bytes()
    assert result.headers["content-type"] == "application/pdf"
    assert result.headers["cache-control"] == "private, no-store"


def test_signed_photo_upload_requires_password_and_valid_signature(client, environment):
    url = build_upload_url("/upload", "test/foto.jpg", 600, SECRET)
    # A URL assinada sozinha não pode dispensar a senha da instalação.
    assert client.put(url, content=b"upload-test").status_code == 401
    assert client.put("/upload?file=foto.jpg&expires=0&signature=x",
                      content=b"upload-test", auth=AUTH).status_code == 400
    assert client.put(url[:-1] + ("0" if url[-1] != "0" else "1"),
                      content=b"upload-test", auth=AUTH).status_code == 400
    result = client.put(url, content=b"upload-test", auth=AUTH)
    assert result.status_code == 200
    assert (environment / "uploads/test/foto.jpg").read_bytes() == b"upload-test"


def test_expired_signed_upload_is_rejected(client, environment):
    url = build_upload_url("/upload", "expired.jpg", -60, SECRET)
    assert client.put(url, auth=AUTH, content=b"data").status_code == 400
    assert not (environment / "uploads/expired.jpg").exists()


def test_oversize_upload_removes_partial_file(client, environment):
    url = build_upload_url("/upload", "test/large.jpg", 600, SECRET)
    response = client.put(url, auth=AUTH, content=b"x" * (30 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert not (environment / "uploads/test/large.jpg").exists()


def test_cross_origin_upload_is_blocked(client, environment):
    url = build_upload_url("/upload", "test/foto.jpg", 600, SECRET)
    assert client.put(url, auth=AUTH, content=b"data",
                      headers={"Origin": "https://outro.invalid"}).status_code == 403
    assert not (environment / "uploads/test/foto.jpg").exists()


def test_websocket_requires_authentication(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pytest.fail("WebSocket sem senha foi aceito")


def test_authenticated_websocket_can_connect_only_from_same_origin(client):
    token = base64.b64encode(f"{AUTH[0]}:{AUTH[1]}".encode()).decode()
    headers = {"Authorization": f"Basic {token}", "Origin": "http://testserver"}
    with client.websocket_connect("/ws", headers=headers):
        pass
    headers["Origin"] = "https://outro.invalid"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers=headers):
            pytest.fail("WebSocket de outra origem foi aceito")


def test_drafts_survive_new_server_instance(app, environment):
    report = Report.new("Casa persistente")
    report.activities[0] = "Atividade preservada após reiniciar"
    app.state.repository.save(report)
    restored_app = create_app()
    restored = restored_app.state.repository.load_all()
    assert restored[0].activities[0] == report.activities[0]
    assert restored_app.state.repository.root == environment.resolve()
    assert DraftRepository(environment).read(environment / "drafts" / f"{report.id}.json").id == report.id


@pytest.mark.parametrize("name,value", [("RSO_USERNAME", ""), ("RSO_PASSWORD", ""),
                                       ("FLET_SECRET_KEY", ""), ("RSO_PASSWORD", "curta"),
                                       ("FLET_SECRET_KEY", "curta"), ("RSO_USERNAME", "a:b")])
def test_server_refuses_missing_or_invalid_secrets(environment, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=name):
        WebConfig.from_env()


def test_render_requires_explicit_storage_directory(environment, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("RSO_DATA_DIR")
    with pytest.raises(RuntimeError, match="RSO_DATA_DIR"):
        WebConfig.from_env()


def test_blueprint_uses_free_plan_without_disk_or_automatic_deploy():
    root = Path(__file__).resolve().parents[1]
    service = yaml.safe_load((root / "render.yaml").read_text())["services"][0]
    assert service["runtime"] == "python"
    assert service["plan"] == "free"
    assert "disk" not in service
    assert service["autoDeployTrigger"] == "off"
    assert service["healthCheckPath"] == "/healthz"
    assert "$PORT" in service["startCommand"] and "--workers 1" in service["startCommand"]
    assert "requirements-web.txt" in service["buildCommand"]
    variables = {v["key"]: v for v in service["envVars"]}
    assert variables["RSO_PASSWORD"].get("sync") is False
    assert variables["FLET_SECRET_KEY"]["generateValue"] is True
    assert variables["RSO_DATA_DIR"]["value"] == "/tmp/rso-data"
    assert variables["RSO_STORAGE_MODE"]["value"] == "ephemeral"
