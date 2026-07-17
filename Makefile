# GisFIRE developer tasks.
#
# Two isolated environments (see CLAUDE.md and the two-venv memory):
#   - project venv (.venv)             : core data model + FastAPI + algorithms
#   - QGIS venv (--system-site-packages): the QGIS plugin, runs in QGIS's Python
#
# Override the QGIS venv path if yours differs:
QGIS_VENV ?= /opt/qgis-gisfire-dev/venv
# PyQGIS (the `qgis` module) lives outside the standard site-packages, so it must
# be added to PYTHONPATH for the venv's python to import it. QT_QPA_PLATFORM
# keeps Qt headless during tests. Override either if your install differs:
QGIS_PYTHONPATH ?= /usr/share/qgis/python
QGIS_QT_PLATFORM ?= offscreen
QGIS_ENV = PYTHONPATH="$(QGIS_PYTHONPATH):$$PYTHONPATH" QT_QPA_PLATFORM=$(QGIS_QT_PLATFORM)

.PHONY: help venv install install-qgis test test-qgis test-all test-full test-qgis-full docs clean

help:
	@echo "make venv           - create the project venv (.venv)"
	@echo "make install        - install core + dev deps into .venv"
	@echo "make install-qgis   - install plugin dev deps into the QGIS venv"
	@echo "make test           - run core tests + coverage (project venv)"
	@echo "make test-qgis      - run plugin tests + coverage (QGIS venv)"
	@echo "make test-all       - run both suites"
	@echo "make test-full      - core: full verbose run + HTML coverage, stop on first fail"
	@echo "make test-qgis-full - plugin: full verbose run + HTML coverage, stop on first fail"
	@echo "make docs           - build the Sphinx docs"
	@echo "make clean          - remove test/coverage artifacts + throwaway QGIS settings"

venv:
	python3 -m venv .venv

install:
	.venv/bin/pip install -r requirements/dev.txt

install-qgis:
	$(QGIS_VENV)/bin/pip install -r requirements/qgis-dev.txt

# Core suite: auto-discovers ./pytest.ini (coverage on by default), collects only test/.
# `python -m pytest` (not the bin/pytest script) so it also works when pytest is
# provided via system-site-packages (as in the QGIS venv).
test:
	.venv/bin/python -m pytest

# Plugins suite: run from qgis_plugins/ so it auto-discovers qgis_plugins/pytest.ini,
# with PyQGIS on PYTHONPATH and Qt headless (see QGIS_ENV above).
test-qgis:
	cd qgis_plugins && $(QGIS_ENV) $(QGIS_VENV)/bin/python -m pytest

test-all: test test-qgis

# Full verbose runs with an HTML coverage report (matches the usual manual command:
# -x stop on first failure, -s no capture, -vv extra-verbose, HTML report dir).
test-full:
	.venv/bin/python -m pytest -x -v --cov-report=html:./test/coverage_reports --cov=./src ./test -s -vv

test-qgis-full:
	cd qgis_plugins && $(QGIS_ENV) $(QGIS_VENV)/bin/python -m pytest -x -v --cov-report=html:./test/coverage_reports --cov=gisfire_thunderstorm --cov=gisfire_minimum_geometric_cover --cov=gisfire_helicopter_routes ./test -s -vv

docs:
	$(MAKE) -C docs html

# Remove regenerated test artifacts, including the throwaway QGIS profile that
# pytest-qgis writes to qgis_plugins/.qgis-settings (QGIS_CUSTOM_CONFIG_PATH).
clean:
	rm -rf test/coverage_reports qgis_plugins/test/coverage_reports
	rm -rf qgis_plugins/.qgis-settings .qgis-settings
	rm -f .coverage qgis_plugins/.coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
