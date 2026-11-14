FMI lightning download (Finland)
================================

Fetches every lightning stroke the Finnish Meteorological Institute's open-data WFS
serves for the years asked for, over the whole area it serves (Northern Europe, 49.7 to
73.1 N, 2.3 to 35.7 E), and writes one file per UTC month. It touches no database; the
files are imported with :doc:`fmi_import_lightnings`. See :doc:`../providers` for the
dataset.

Usage
-----

.. code-block:: console

   # one year
   python3 -m src.apps.download.lightnings.finland_fmi.download_lightnings \
       --from-year 2018 --output-dir ~/data/fmi

   # several years, both included
   python3 -m src.apps.download.lightnings.finland_fmi.download_lightnings \
       --from-year 1998 --to-year 2025 --output-dir ~/data/fmi

``--from-year`` is required and ``--to-year`` defaults to it. The archive starts in
1998, so an earlier year is refused, and so is a year that has not started.
``--overwrite`` fetches again the months already on disk; ``--include-current`` also
fetches the months not complete yet (see below). ``--delay`` (seconds between requests,
default 1), ``--retries`` (default 4), ``--timeout`` (default 300 s) and ``--url`` tune
the client; ``--log-level`` the verbosity. No service key is needed.

What it asks for
----------------

The stored query ``fmi::observations::lightning::multipointcoverage``, the compact
encoding of the strokes — a list of ``latitude longitude unixtime`` positions beside a
list of value tuples, a small fraction of the size of ``…::simple``, which returns the
same records — with all **sixteen** parameters named, since without them the service
returns only four. There is no ``bbox``: the whole served area.

The service takes the interval ``[starttime, endtime)`` — the end excluded — of **at most
168 hours**, and refuses a longer one with HTTP 400. Each month is therefore cut into
windows of at most 168 hours that end exactly at the month's end: consecutive windows
neither overlap nor leave a gap, and none crosses into the next month. A 31-day month is
five requests, a year 59, so 1998 to 2025 is about 1,650.

What it writes
--------------

For each month, in ``--output-dir``:

``fmi_lightning_YYYY-MM.csv.gz``
    A header — ``unixtime``, ``latitude``, ``longitude`` and the sixteen parameters —
    then one row per stroke, **every value the text the service sent**: nothing is
    converted or rounded, and the rows of a window keep the service's order. Latitude
    comes first, as the service sends it.
``fmi_lightning_YYYY-MM.meta.json``
    Where the data came from: the endpoint, the stored query and the parameters, every
    window with its stroke count and the server's timestamp, the download time, the
    licence and the attribution, the columns, and whether the month is **complete**.

The data file is written to a ``.part`` and renamed only when every window of the month
has arrived and passed the checks, and the sidecar is written after it. If a window
fails, nothing of the month is left on disk and the files already there stay as they
were. A month with both files and a sidecar saying it is complete is skipped by the next
run, so an interrupted run resumes where it stopped. The data is taken as final: a
complete month is fetched again only with ``--overwrite``.

The month in progress
---------------------

A month counts as complete **one day after it ends**, so that its last strokes have
reached the archive; the year in progress therefore stops at the last complete month.
``--include-current`` adds the months not yet complete, fetched up to now: their sidecar
says ``"complete": false``, every later run fetches them again, and the importer warns
about them.

What is checked
---------------

Every response, before anything of it is written:

- it is XML, and not an ``ExceptionReport`` — the service's answer to a bad request,
  reported with its text (an interval too long, an unknown parameter);
- it holds at most one coverage, whose fields are the sixteen parameters **in the order
  asked for**;
- its positions are ETRS89 with a Unix time;
- there are as many value tuples as positions, three numbers per position and sixteen per
  tuple, and no value holds a comma;
- every stroke falls inside its window.

A window with no stroke is an empty collection, which is fine.

Being a polite client
---------------------

The service allows 600 requests every five minutes and 20,000 a day. The client waits
``--delay`` seconds between the *start* of one request and the next; retries timeouts,
lost connections, HTTP 429 and 5xx with exponential backoff, and nothing else — a 400 is
a bad request that no retry will change; and sends a ``User-Agent`` that says who is
calling.

The run ends with the strokes per month. 2018, for instance — 59 requests, two
minutes, 45 MB of files:

.. code-block:: text

     Month          Strokes
     --------- ------------
     2018-01            241
     ...
     2018-07        906,338
     2018-08        736,404
     ...
     2018-12            210

A busy week is half a million strokes and 42 MB of XML, and takes about 20 seconds; the
busiest week parses in two seconds and about 300 MB of memory, and only one window is
held at a time.

.. note::

   FMI open data is licensed **CC BY 4.0**: attribution required, redistribution
   allowed. Credit it as *Finnish Meteorological Institute (FMI), open data, CC BY 4.0*;
   the sidecar records it.

Where to run it
---------------

It needs only the network and a disk, so run it where the files should end up — on the
server, if that is where they will be imported. :doc:`running_on_a_server` explains every
part of the commands below.

**Locally**:

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.download.lightnings.finland_fmi.download_lightnings \
       --from-year 2018 --output-dir ~/data/fmi

**On the server, over SSH**, detached with ``nohup`` so you can log out while it runs (the
whole archive takes the better part of an hour):

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.download.lightnings.finland_fmi.download_lightnings \
       --from-year 1998 --to-year 2025 --output-dir ~/data/fmi \
       > fmi_download_lightnings.log 2>&1 < /dev/null &
   exit

When you log in again, check on it:

.. code-block:: bash

   cd ~/GisFIRE
   tail -f fmi_download_lightnings.log    # Ctrl-C stops tail, not the run
   pgrep -af finland_fmi.download_lightnings    # still running?
   grep -E 'ERROR|WARNING' fmi_download_lightnings.log

An interrupted run is resumed by running the same command again: the complete months are
skipped.

API reference
-------------

.. automodule:: src.apps.download.lightnings.finland_fmi.download_lightnings
   :members:
   :show-inheritance:
