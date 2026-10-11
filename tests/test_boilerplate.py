"""Behavior required from the reference API adapted from touchpoint-taxonomy."""

import logging
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.app import app_factory
from app.settings import Settings, get_settings
from pg_task_engine import __version__


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never read the developer's actual dotenv file during these tests."""
    monkeypatch.setenv("SETTINGS_ENV", str(tmp_path / "missing.env"))
    for variable in ("APP_NAME", "DEBUG", "APP_ROOT_PATH", "CORS_ORIGINS"):
        monkeypatch.delenv(variable, raising=False)


async def test_version_endpoint_matches_library_distribution() -> None:
    application = app_factory()
    async with (
        LifespanManager(application) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as client,
    ):
        response = await client.get("/version")
    assert response.status_code == 200
    assert response.json() == __version__


async def test_liveness_does_not_claim_database_or_worker_readiness() -> None:
    application = app_factory()
    async with (
        LifespanManager(application) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as client,
    ):
        alive = await client.get("/health/live")
        ready = await client.get("/health/ready")
        jobs = await client.get("/jobs")
    assert alive.status_code == 200
    assert alive.json() == {"status": "alive"}
    assert ready.status_code == 404
    assert jobs.status_code == 404


async def test_openapi_exposes_only_reference_endpoints() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_factory()),
        base_url="http://test",
    ) as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert set(response.json()["paths"]) == {"/version", "/health/live"}
    assert response.json()["info"]["version"] == __version__


def test_app_factory_reads_environment_each_time(monkeypatch: pytest.MonkeyPatch) -> None:
    first = app_factory()
    monkeypatch.setenv("APP_NAME", "Configured reference API")
    monkeypatch.setenv("APP_ROOT_PATH", "/task-api")
    second = app_factory()
    assert first.title == "pg-task-engine API"
    assert first.root_path == ""
    assert second.title == "Configured reference API"
    assert second.root_path == "/task-api"
    assert first is not second


def test_default_settings_require_no_cloud_or_corporate_credentials() -> None:
    settings = get_settings()
    assert settings.DEBUG is False
    assert settings.CORS_ORIGINS == []
    assert "KEYCLOAK_URL" not in Settings.model_fields
    assert "GCP_PROJECT_ID" not in Settings.model_fields


def test_settings_env_supports_explicit_dotenv_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv = tmp_path / "reference.env"
    dotenv.write_text("APP_NAME=From dotenv\nDEBUG=false\n", encoding="utf-8")
    monkeypatch.setenv("SETTINGS_ENV", str(dotenv))
    settings = get_settings()
    assert settings.APP_NAME == "From dotenv"
    assert settings.DEBUG is False


def test_environment_overrides_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dotenv = tmp_path / "reference.env"
    dotenv.write_text("APP_NAME=From dotenv\n", encoding="utf-8")
    monkeypatch.setenv("SETTINGS_ENV", str(dotenv))
    monkeypatch.setenv("APP_NAME", "From environment")
    assert get_settings().APP_NAME == "From environment"


@pytest.mark.parametrize("value", ["relative-path", "not/a/root"])
def test_settings_reject_relative_root_path(value: str) -> None:
    with pytest.raises(ValidationError, match="APP_ROOT_PATH"):
        Settings(APP_ROOT_PATH=value)


async def test_unknown_origin_is_not_allowed_by_default() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_factory()),
        base_url="http://test",
    ) as client:
        response = await client.get("/version", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in response.headers


async def test_explicit_cors_origin_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:4200"]')
    async with AsyncClient(
        transport=ASGITransport(app=app_factory()),
        base_url="http://test",
    ) as client:
        response = await client.get("/version", headers={"Origin": "http://localhost:4200"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"


def test_app_factory_does_not_reconfigure_root_logging() -> None:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    app_factory()
    assert root.handlers == original_handlers
    assert root.level == original_level
