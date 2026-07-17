# GisFIRE QGIS plugins

This directory is a **container for several independent QGIS v4 plugins**, not a
single plugin and not a Python package itself. Each subfolder is one deployable
plugin (its own `metadata.txt` + `classFactory`), imported by QGIS as a top-level
package named after the folder:

| Plugin (metadata name)          | Folder / package                   |
| ------------------------------- | ---------------------------------- |
| GISFire Thunderstorm            | `gisfire_thunderstorm`             |
| GISFire Minimum Geometric Cover | `gisfire_minimum_geometric_cover`  |
| GISFire Helicopter Routes       | `gisfire_helicopter_routes`        |

## Runtime & dependency rules

- These run **inside QGIS's own Python** (Qt6 / PyQt6), never in the core project
  venv. Develop/test them from the QGIS venv (`--system-site-packages`); install
  deps with `make install-qgis`. See `SETUP_DEV.md`.
- Dependency direction is one-way and thin: plugins talk to the backend over the
  HTTP API (`requests`) and must **not** import the server / data-model packages
  (no SQLAlchemy / FastAPI / psycopg here). Shared types, if ever needed, go in a
  small pure-Python `gisfire-common` package.

## Tests

Central per-plugin tests live under `test/<plugin_package>/`. Run them with
`make test-qgis` (or `make test-qgis-full` for verbose + HTML coverage), which
puts PyQGIS on `PYTHONPATH` and runs Qt headless.
