Import IGN administrative boundaries
====================================

Imports the Spanish administrative divisions — *comunidades autónomas*,
*provincias* and *municipios* — from the IGN's ``recintos`` shapefiles into
:class:`~src.providers.spain_ign.admin_boundary.IgnAdminBoundary` rows, as administrative
levels 1, 2 and 3 below the country. See :doc:`../providers/ign_provider` for the
dataset.

.. contents::
   :local:
   :depth: 2

Usage
-----

Point the application at the directory the IGN download was unpacked into. It is
searched recursively, so the argument can be the download root — which holds a
directory per datum, each holding a directory per level — or a single datum's
folder:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.ign.import_admin_boundaries -d /path/to/bddae

Database settings are read from the environment (``.env``, see
:doc:`../setup/configuration`) and each can be overridden on the command line —
``--db-host``, ``--db-port``, ``--db-name``, ``--db-user``, ``--db-password``.

.. important::

   The application shells out to **ogr2ogr**, which comes with GDAL and must be on
   ``PATH``. It is a system package, not a Python dependency:

   .. code-block:: bash

      sudo apt install gdal-bin      # Debian/Ubuntu

Import the countries first
^^^^^^^^^^^^^^^^^^^^^^^^^^

The BDDAE publishes no Spain polygon — the top level is the *comunidad autónoma* —
so those are parented to the country boundary the OCHA import loads at level 0:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.ocha.import_admin_boundaries -g adm0_polygons.gpkg
   python3 -m src.apps.imports.admin_boundaries.ign.import_admin_boundaries -d /path/to/bddae

Running them the other way round is not a mistake to undo by hand: the *comunidades*
are imported as roots, and **re-running this import once the countries are there
links them**. That is a deliberate step in the application, since
``ON CONFLICT DO NOTHING`` skips rows that already exist and would never fill the
parent in.

What is imported
----------------

=====================  ==========  =========  ======================
Level                  Code width  ``level``  Count (2026)
=====================  ==========  =========  ======================
*Comunidad autónoma*   4           1          19
*Provincia*            6           2          52
*Municipio*            11          3          8 213
=====================  ==========  =========  ======================

8 284 boundaries. The ``recintos`` layers are the areas; the companion ``ll_*``
layers hold the boundary *lines* and are never picked up, since an area is what a
fire is attributed to.

Of the 8 213 *municipios*, **81 are not INE municipalities** but *condominios*,
*comuneros*, *facerías* and *parzonerías* — land shared between municipalities,
which the IGN maps at the same level and gives a pseudo-province code of ``53``.
They are kept: they are real ground that can burn, and dropping them would leave
holes in the coverage. That leaves 8 132 actual municipalities, which is the INE's
own count.

How it works
------------

Two datums, six shapefiles
^^^^^^^^^^^^^^^^^^^^^^^^^^

The data is published twice, once per datum: the peninsula and the Balearics in
**ETRS89** (EPSG:4258) and the Canaries in **REGCAN95** (EPSG:4081), with the three
levels in a ``recintos_*`` directory each.

Both are *geographic* CRSs on the GRS80 ellipsoid, and both declare a null
transformation to WGS84 — so unlike the CAOP's four projected grids, reprojecting
to EPSG:4326 does not move a coordinate:

.. code-block:: text

   -3.7038 40.4168  (4258 → 4326)  ->  -3.7038 40.4168
   -15.4300 28.1235 (4081 → 4326)  ->  -15.4300 28.1235

``ogr2ogr`` is still told to do it, so the import does not quietly depend on the
source never changing.

The codes nest, but they are padded
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``NATCODE`` is 11 digits at **every** level, zero-padded on the right — ``34``
(Spain) + *comunidad* (2) + *provincia* (2) + the INE municipal code (5):

.. code-block:: text

   34170000000   La Rioja                (comunidad autónoma)
   34172600000   La Rioja                (provincia)
   34172626145   Sotés                   (municipio, INE code 26145)

So each level is staged and mapped in turn, largest division first, and the parent
is found by code with the padding put back:

.. code-block:: sql

   parent.source_id = left(staging.natcode, 6) || '00000'

not by a plain prefix as for the Portuguese CAOP, and not by a spatial containment
test. Checked over the whole dataset: no unit at any level fails to find its parent
that way.

NUTS needs no reconciling
-------------------------

Portugal's NUTS 3 regions cross *distrito* boundaries, which forced the CAOP import
to choose which hierarchy would be the tree (see
:doc:`../providers/caop_provider`). Spain's do not:

- ``CODNUT2`` maps one-to-one onto the *comunidad autónoma*.
- **No NUTS 3 region spans more than one province.** It equals the province
  everywhere except three island provinces, where it splits further — one region
  per island.

NUTS 3 is therefore a refinement of the administrative tree, not a rival to it, and
the codes are carried as plain columns with nothing to decide. They are the full
Eurostat codes (``ES230``), not the national short form the CAOP publishes.

One asymmetry: the IGN fills ``CODNUT3`` on *municipios* only, leaving it empty at
both levels above. It is stored as ``NULL`` there rather than derived.

What is left out, and why
-------------------------

The IGN maps seven areas as ``NATLEVNAME = 'Territorio'`` rather than
``'Municipio'``, under a pseudo *comunidad autónoma* and a pseudo *provincia* that
exist only to hold them:

.. code-block:: text

   Gibraltar, Isla de los Faisanes, Isla del Perejil, Islas Chafarinas,
   Islas Alhucemas, Peñón de Alhucemas, Peñón de Vélez de la Gomera

Those nine rows — the seven areas plus the two pseudo levels — are **excluded by
default**. They are not Spanish administrative divisions in the sense the rest of
the dataset is, the IGN's own level name says as much, and Gibraltar is a separate
country in the OCHA boundaries GisFIRE already imports, so keeping it here would
put one place in the tree twice under two sovereigns.

The whole branch is the codes beginning ``3420``, which selects exactly those nine
rows and nothing else. To keep them:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.ign.import_admin_boundaries \
       -d /path/to/bddae --include-territories

They then arrive with
:attr:`~src.providers.spain_ign.admin_boundary.IgnAdminBoundary.kind` set to
``territorio``, at the same ``level`` as a *municipio* but distinguishable from one.

Editions live side by side
--------------------------

Spanish municipalities merge and split, so the codes are not stable for ever. Each
publication is imported as its own
:class:`~src.data_model.data_provider.DataProvider` row — ``IGN`` /
``Base de Datos de Divisiones Administrativas de España 2026`` — which is what
``uq_admin_boundary_provider_source`` is scoped by:

.. code-block:: bash

   python3 -m src.apps.imports.admin_boundaries.ign.import_admin_boundaries \
       -d /path/to/bddae2019 --edition 2019

Without that, importing a second edition would import *nothing*: every code would
collide with the first edition's and be silently skipped.

.. warning::

   Nothing in the published files names the edition — not the file names, not the
   DBFs, not the ``Leeme`` document. So ``--edition`` cannot be checked against the
   data the way the CAOP import checks it against the file names, and it is simply
   what the operator says it is. Getting it wrong merges two publications of Spain
   into one provider.

Joining Spanish data to it
--------------------------

The last five digits of ``NATCODE`` are the **INE** municipal code, a different
numbering system embedded in the IGN's own. It is what the INE's tables and the
EGIF wildfire statistics join on, so it is stored in its own indexed column rather
than left to be sliced out:

.. code-block:: sql

   SELECT boundary.name, ST_PointOnSurface(boundary.geometry)
   FROM admin_boundary boundary
   JOIN ign_admin_boundary ign ON ign.id = boundary.id
   WHERE ign.kind = 'municipio' AND ign.edition = '2026' AND ign.ine_code = '26145';

It is text, not a number: codes such as ``01001`` would lose their leading zero.

API reference
-------------

.. automodule:: src.apps.imports.admin_boundaries.ign.import_admin_boundaries
   :members:
