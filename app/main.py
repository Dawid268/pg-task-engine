"""ASGI entry point matching the source boilerplate layout."""

from app.app import app_factory

app = app_factory()
