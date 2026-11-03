"""Process-wide extractor used by the API and the MCP server."""

from __future__ import annotations

from functools import cache

from docfunnel.config import Settings, build_extractor
from docfunnel.extractor import Extractor


@cache
def get_settings() -> Settings:
    return Settings.from_env()


@cache
def get_extractor() -> Extractor:
    return build_extractor(get_settings())
