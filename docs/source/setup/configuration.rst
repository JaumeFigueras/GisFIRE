Configuration (``.env``)
========================

.. contents::
   :local:
   :depth: 2

Overview
--------

Everything that varies between machines — database host, credentials, the port the API
listens on — is read from **environment variables**, never hard-coded and never
committed. At the repository root, :mod:`src.settings` loads a ``.env`` file into the
environment on import, and Alembic, the FastAPI backend and the import applications all
read their configuration from there.

Real environment variables always take precedence over the file (``load_dotenv`` is
called with ``override=False``), so a deployment can export the variables the usual way
— systemd unit, container environment, CI secrets — and never ship a ``.env`` at all.

Creating your ``.env``
----------------------

``.env.example`` is committed and documents every variable the project reads. Copy it
and fill in the real values:

.. code-block:: bash

   cp .env.example .env
   $EDITOR .env

``.env`` is listed in ``.gitignore`` and **must never be committed** — it holds real
credentials. When you add a new variable, add it to ``.env.example`` too (with a safe
placeholder), so the file stays the single description of what the project needs.

Variables
---------

.. list-table::
   :header-rows: 1
   :widths: 30 15 55

   * - Variable
     - Default
     - Meaning
   * - ``GISFIRE_DB_HOST``
     - ``localhost``
     - Host of the PostgreSQL server.
   * - ``GISFIRE_DB_PORT``
     - ``5432``
     - Port of the PostgreSQL server.
   * - ``GISFIRE_DB_NAME``
     - *required*
     - Database name.
   * - ``GISFIRE_DB_USER``
     - *required*
     - Database user.
   * - ``GISFIRE_DB_PASSWORD``
     - empty
     - Database password. Omitted from the URL when empty (peer/trust authentication).
   * - ``GISFIRE_API_HOST``
     - ``127.0.0.1``
     - Address the FastAPI/uvicorn server binds to.
   * - ``GISFIRE_API_PORT``
     - ``8000``
     - Port the FastAPI/uvicorn server binds to.
   * - ``GISFIRE_LOG_LEVEL``
     - ``INFO``
     - Logging verbosity.

The two required variables have no default on purpose: a missing ``GISFIRE_DB_NAME`` or
``GISFIRE_DB_USER`` raises :exc:`RuntimeError` instead of quietly connecting to some
unintended database.

Using it in code
----------------

:func:`src.settings.database_url` assembles the SQLAlchemy URL from those variables,
URL-encoding the user and password so special characters in a password cannot corrupt
it:

.. code-block:: python

   from sqlalchemy import create_engine

   from src.settings import database_url

   engine = create_engine(database_url())

API reference
-------------

.. automodule:: src.settings
   :members:
   :show-inheritance:
