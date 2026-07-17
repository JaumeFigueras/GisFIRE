"""Smoke test for the core project venv.

Confirms the project package imports in the plain `.venv` (no QGIS/Qt here).
Replace/extend as the port from GisFIRE2 lands.
"""


def test_src_imports():
    import src  # noqa: F401
