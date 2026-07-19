#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Environment-based configuration.

Every tool that needs to reach the database or the API — Alembic, FastAPI, the
import applications — reads its settings from environment variables, loaded from
a ``.env`` file at the repository root if one is present (see ``.env.example``).
Real environment variables always win over the file, so deployments can set them
the usual way and ignore ``.env`` entirely.

Kept deliberately small: plain :func:`os.getenv` lookups, no settings framework.
"""

from __future__ import annotations

import os

from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

#: Repository root, i.e. the directory holding ``.env``.
ROOT_DIR = Path(__file__).resolve().parent.parent

# ``override=False`` so an already-exported variable beats the file.
load_dotenv(ROOT_DIR / ".env", override=False)


def database_url(*, driver: str = "postgresql+psycopg") -> str:
    """Build the SQLAlchemy database URL from the environment.

    Parameters
    ----------
    driver : str
        SQLAlchemy dialect+driver prefix. Defaults to psycopg 3.

    Returns
    -------
    str
        A URL such as
        ``postgresql+psycopg://user:password@localhost:5432/gisfire``.

    Raises
    ------
    RuntimeError
        If a variable with no sensible default (``GISFIRE_DB_NAME``,
        ``GISFIRE_DB_USER``) is missing, rather than silently connecting
        somewhere unintended.
    """
    host = os.getenv("GISFIRE_DB_HOST", "localhost")
    port = os.getenv("GISFIRE_DB_PORT", "5432")
    name = _required("GISFIRE_DB_NAME")
    user = _required("GISFIRE_DB_USER")
    password = os.getenv("GISFIRE_DB_PASSWORD", "")

    credentials = f"{quote_plus(user)}:{quote_plus(password)}" if password else quote_plus(user)
    return f"{driver}://{credentials}@{host}:{port}/{name}"


def _required(variable: str) -> str:
    """Return the value of ``variable`` or raise if it is unset or empty."""
    value = os.getenv(variable)
    if not value:
        raise RuntimeError(
            f"Environment variable {variable} is not set. Copy .env.example to .env and fill it in."
        )
    return value
