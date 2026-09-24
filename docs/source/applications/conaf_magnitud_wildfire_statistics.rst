CONAF *incendios de magnitud* burnt-area statistics (Chile)
===========================================================

Counts CONAF's mapped perimeters and measures the area inside them, by country and by
season, beside the area the bound *report* claims for the same fires. Writes CSV or a Word
document.

Usage
-----

.. code-block:: console

   $ python3 -m src.apps.statistics.wildfires.chile_conaf_magnitud.wildfire_statistics \
         --csv magnitud.csv

   $ python3 -m src.apps.statistics.wildfires.chile_conaf_magnitud.wildfire_statistics \
         -y 2016 --docx magnitud-2016.docx

   # measure the polygons now, geodesically, instead of trusting the published figure
   $ python3 -m src.apps.statistics.wildfires.chile_conaf_magnitud.wildfire_statistics \
         --area-method geodesic --csv magnitud-geodesic.csv

   # only the perimeters the binder placed, where both area columns are comparable
   $ python3 -m src.apps.statistics.wildfires.chile_conaf_magnitud.wildfire_statistics \
         --bound-only --csv magnitud-bound.csv

Run :doc:`conaf_magnitud_import_wildfires` first, and
:doc:`conaf_magnitud_bind_wildfires` before relying on the ``Reported`` column. One of
``--csv`` or ``--docx`` is required.

Where to run it
---------------

The same command can be run in three ways, depending on where the database is.
:doc:`running_on_a_server` explains every part of the commands below. The report only
reads the database, and what it writes (``--csv``, ``--docx``) lands on the machine
the command runs on.

**Locally**, with the database on this machine and ``.env`` pointing at it:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.statistics.wildfires.chile_conaf_magnitud.wildfire_statistics \
       --csv magnitud.csv

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs.
Relative output paths are relative to ``~/GisFIRE`` on the server:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.statistics.wildfires.chile_conaf_magnitud.wildfire_statistics \
       --csv magnitud.csv \
       > chile_conaf_magnitud_wildfire_statistics.log 2>&1 < /dev/null &
   exit

When you log in again, check on it, then copy the report back to your machine:

.. code-block:: bash

   ssh user@server 'pgrep -af chile_conaf_magnitud.wildfire_statistics; tail -n 20 GisFIRE/chile_conaf_magnitud_wildfire_statistics.log'
   scp user@server:GisFIRE/magnitud.csv .

**From your machine, against the server's database**, through an SSH tunnel to its
PostgreSQL. This is usually the most convenient form for a report. The aggregation runs
on the server and only the summary rows cross the network, and the files are written
straight onto your machine. The password is read into the environment rather than
passed as ``--db-password``, which would show in ``ps`` and in the shell history:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.statistics.wildfires.chile_conaf_magnitud.wildfire_statistics \
       --csv magnitud.csv \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel

Being read-only, the report can also run as ``gisfire_remoteuser``, provided that role has been
granted ``SELECT`` (see :ref:`pg-readonly-grants`).

Mapped against Reported
-----------------------

Two columns, and **two different measurements of the same fires**. ``Mapped`` comes from
the polygon; ``Reported`` is
:attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.area_ha_total` from the seasonal
report the binder attached to it.

.. important::

   A perimeter that is **not bound** contributes to ``Mapped`` and nothing to
   ``Reported``. The report logs how many are like that rather than letting the two
   columns quietly disagree, and ``--bound-only`` narrows the scope to the fires for
   which the comparison is about the same set of rows.

Three ways to measure a polygon
-------------------------------

``published``
    The figure computed at import, on the UTM grid the polygon came on. The default, and
    the cheapest: it is a stored column.

``geodesic``
    Measured now on the WGS84 ellipsoid, from the EPSG:4326 perimeter.

``equal-area``
    Measured now in EPSG:6933, NSIDC EASE-Grid 2.0 Global.

.. note::

   The two measured methods work from the **EPSG:4326** perimeter rather than from the
   published grid copy, so that they mean the same thing for a mainland fire and for the
   Rapa Nui one. Those are on grids seven zones apart, and areas measured on them could
   not otherwise be added together at all.

Over the real archive the geodesic and the published figures differ by about 0.11%, which
is what a projection difference of this size looks like. Offering all three rather than
picking one is what lets a reader see how much of an answer is the projection.

``--min-area`` applies to whichever method was chosen, so the fires in scope change with
it — which is the intended behaviour: *fires of 500 ha or more* is a question about a
measurement, and the measurement is the thing being selected.

API reference
-------------

.. automodule:: src.apps.statistics.wildfires.chile_conaf_magnitud.wildfire_statistics
   :members:
   :show-inheritance:
