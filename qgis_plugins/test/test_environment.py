"""Shared smoke test: confirms the QGIS test environment is wired up.

Runs only inside the QGIS venv (--system-site-packages) where pytest-qgis
provides a headless QgsApplication.
"""


def test_qgis_application_boots(qgis_app):
    assert qgis_app is not None
