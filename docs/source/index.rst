GisFIRE documentation
=====================

**GisFIRE** implements algorithms and applications to deal with wildfires — from data
preparation and modelling to operational logistics for aerial firefighting.

It brings together:

- **Data processing** pipelines integrating wildfire perimeters, lightning strike
  datasets, meteorological observations and geographic information.
- **Algorithms** for linking lightning events to wildfire ignitions through
  spatial–temporal analysis.
- **Machine learning** models for pre-ignition classification and thunderstorm
  characterization, including techniques for strongly imbalanced datasets.
- **Optimization algorithms** for aerial firefighting: minimum geometric coverage of
  lightning events, helicopter route planning and resource allocation.

The project exposes its functionality through a backend **HTTP API** (FastAPI) served
by an ASGI server behind Apache, a **PostgreSQL/PostGIS** database accessed through
SQLAlchemy + GeoAlchemy2, and a set of **QGIS v4 plugins** that consume the API.

.. note::

   GisFIRE is the successor of the *GisFIRE2* research code base. Its implementation is
   being ported/merged here; some sections below describe structure that is scaffolded
   and filled in as the port progresses.

The documentation is organized as follows:

- **Setup** — environments, the ``Makefile`` workflow, database and documentation.
- **Data Model** — entities, mixins and the multi-CRS metaclass.
- **Applications** — the domain command-line applications.
- **QGIS Plugins** — the suite of QGIS v4 plugins.
- **Auxiliary Applications** — database/DDL helper command-line tools.
- **Auxiliary Modules** — geographic, exception and JSON helper modules.
- **Testing** — the test strategy, fixtures and coverage.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   setup
   data_model
   applications
   qgis_plugins
   auxiliary_applications
   auxiliary_modules
   testing
