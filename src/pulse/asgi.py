"""Configured ASGI entry point for Uvicorn and Docker."""

from pulse.api import create_app
from pulse.config import Settings

app = create_app(Settings.from_env())
