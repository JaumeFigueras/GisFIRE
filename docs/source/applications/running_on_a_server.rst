Running the applications on a server
====================================

.. contents::
   :local:
   :depth: 2

The *Usage* section of every import page shows the command as you would type it on the
machine that holds both the data files and the database. That works for a laptop, but the
full imports run for minutes to hours, and on a server you want to start them, close the
SSH connection and come back later for the result. Every import, binding, resync and
statistics page therefore has a **Where to run it** section with its own command written
three ways:

.. list-table::
   :header-rows: 1
   :widths: 22 26 26 26

   * -
     - Locally
     - On the server, over SSH
     - Against a remote database
   * - Where the command runs
     - your machine
     - the server
     - your machine
   * - Where the files are
     - your machine
     - the server
     - your machine
   * - Where the database is
     - your machine
     - the server
     - the server
   * - Database settings from
     - local ``.env``
     - server's ``.env``
     - ``--db-*`` options
   * - Survives closing the terminal
     - no
     - **yes** (``nohup``)
     - no — use ``nohup`` too if it must

This page explains the pieces those commands are made of. The examples use the GWIS
import; the others are the same apart from the module and its arguments.

Locally
-------

The plain case: the repository is checked out, the virtual environment exists and
``.env`` points at a database on this machine (see
:doc:`../setup/postgresql_database` and :doc:`../setup/configuration`).

.. code-block:: bash

   cd ~/GisFIRE && source .venv/bin/activate
   python3 -m src.apps.imports.wildfires.gwis.import_wildfires -d /path/to/zip/

Run from the repository root: ``python3 -m src.apps...`` resolves the ``src`` package
relative to the current directory. ``.env`` is found wherever you run it from, because
:mod:`src.settings` looks for it next to ``src/``.

On the server, over SSH
-----------------------

The data files are copied to the server first (``rsync -avP /path/to/zip/
user@server:/data/gwis/``), and the repository, its ``.venv`` and a ``.env`` pointing at
the server's own cluster (``localhost``, port ``5433``) exist there too. Then:

.. code-block:: bash

   ssh user@server
   cd ~/GisFIRE
   nohup .venv/bin/python -u -m src.apps.imports.wildfires.gwis.import_wildfires \
       -d /data/gwis/ \
       > gwis_import_wildfires.log 2>&1 < /dev/null &
   exit

What each part does:

``nohup``
    Makes the process ignore ``SIGHUP``, the signal the shell sends its children when the
    SSH connection closes. Without it, logging out — or a dropped connection — kills the
    import halfway through a file.

``.venv/bin/python``
    The virtual environment's interpreter, by path. ``source .venv/bin/activate`` would
    work too, but the path is explicit and still correct if you paste the line into a
    shell where the environment is not active.

``-u``
    Unbuffered output. Redirected to a file, Python's standard output is block-buffered,
    so lines would reach the log in 8 kB bursts, or only at the end. The log messages go
    to standard error and are written straight away regardless; ``-u`` makes everything
    else do the same, so the log is always current.

``> gwis_import_wildfires.log 2>&1``
    Standard output *and* standard error to one file, in the order they happened. Without
    a redirection ``nohup`` writes to ``nohup.out``, and every run would append to the
    same file. ``*.log`` is in ``.gitignore``, so a log in the repository root is never
    committed by accident.

``< /dev/null``
    Nothing to read from the terminal that is about to disappear. It also silences the
    ``nohup: ignoring input`` message.

``&``
    Runs it in the background, returning the prompt so you can log out.

The progress bars behave well in a log. When their output is not a terminal they write
an ordinary log line every so many items instead of redrawing one line (see
:class:`~src.apps.imports.common.ProgressReporter` and
:class:`~src.apps.imports.common.Spinner`), and ``ogr2ogr``'s ``0...10...20`` bar is a
single line anyway. The log shows how far the import got without being full of control
characters. Keep ``--log-level`` at ``INFO`` for these
runs. The log is the only record of the run, and the per-file lines are what show where
an interrupted import stopped.

Using the server's cores
^^^^^^^^^^^^^^^^^^^^^^^^

Two importers can import several files at once with ``--jobs N``:
:doc:`gwis_import_wildfires` (one archive per year) and :doc:`gfa_import_wildfires`
(one shapefile per year). The default is ``1``. PostgreSQL does not parallelise a
statement that writes, so a serial run keeps **one** server core busy whatever the
machine has. On a server, pass ``--jobs`` explicitly: 4 is a safe start, and around 6
suits 12 cores once the cluster is tuned (:ref:`pg-tuning`). Each page explains the
limits. The other importers have no ``--jobs`` option and always run serially.

Coming back later
^^^^^^^^^^^^^^^^^

Log in again from anywhere:

.. code-block:: bash

   cd ~/GisFIRE
   tail -f gwis_import_wildfires.log      # follow it; Ctrl-C stops tail, not the import
   pgrep -af gwis.import_wildfires        # still running? prints its PID and command line
   grep -E 'ERROR|WARNING' gwis_import_wildfires.log

Stopping a run
^^^^^^^^^^^^^^

Every archive, file or year is imported in a transaction of its own, so an interrupted
run keeps what it had finished and loses only the unit in progress. The page of each
importer says what the unit is and what a second run does with data already imported.

Stopping it takes **two steps, not one**. Killing the Python process does not stop the
work it had asked PostgreSQL to do. A backend running a long ``INSERT ... SELECT`` does
not notice that its client has gone until it tries to send the result back, and that
only happens when the statement finishes, possibly hours later. Only then does it fail
and roll back. So after ``kill``, the server keeps using a core per statement that was
running, for nothing. The same goes for an ``ogr2ogr`` that was loading a staging table:
it is a separate process and keeps running after its parent is killed.

1. Kill the client processes: the importer, its ``--jobs`` workers (they have the same
   command line) and any ``ogr2ogr`` it started:

   .. code-block:: bash

      pkill -f gwis.import_wildfires
      pkill -f 'ogr2ogr.*staging\.gwis'

2. Cancel what the database is still running for them. ``gisfire_user`` may cancel its
   own backends, so no superuser is needed:

   .. code-block:: bash

      psql -h localhost -p 5433 -U gisfire_user -d gisfire_db -c "
        SELECT pid, state, now() - query_start AS running, left(query, 60) AS query
          FROM pg_stat_activity
         WHERE usename = 'gisfire_user' AND pid <> pg_backend_pid();"

      psql -h localhost -p 5433 -U gisfire_user -d gisfire_db -c "
        SELECT pg_cancel_backend(pid)
          FROM pg_stat_activity
         WHERE usename = 'gisfire_user' AND state = 'active' AND pid <> pg_backend_pid();"

   ``pg_cancel_backend`` cancels the current statement, and the transaction rolls
   back. If a backend is still listed after a few seconds, ``pg_terminate_backend(pid)``
   closes its connection outright. Both are safe: rolling back in PostgreSQL only
   marks the transaction aborted. It does not undo rows one by one, so it is immediate
   however much had been inserted. Autovacuum later reclaims the space those rows took.

   The ``WHERE`` clause matches **every** session of the role, including a QGIS or
   ``psql`` session of your own that happens to be running a query. Check the first
   listing before cancelling, and use ``WHERE pid IN (...)`` if anything else shows up.

Whatever staging tables were left behind (``staging.<table>`` or ``staging.<table>_NN``)
need no cleanup. The next run's ``ogr2ogr -overwrite`` replaces them.

PostgreSQL 14+ can also detect a client that has gone away while a query is still running:
``client_connection_check_interval = 10s`` in the cluster configuration makes backends
check the socket every 10 seconds and abort on their own when the client is gone. It is
off by default.

Keeping the exit status
^^^^^^^^^^^^^^^^^^^^^^^

A background process's exit status is lost once the shell that started it exits, and a
run that ended in a traceback can look, from the last lines of the log, very much like
one that finished. To have the result written into the log itself, wrap the command:

.. code-block:: bash

   nohup sh -c '.venv/bin/python -u -m src.apps.imports.wildfires.gwis.import_wildfires \
                   -d /data/gwis/; echo "exit status: $?"' \
       > gwis_import_wildfires.log 2>&1 < /dev/null &

``exit status: 0`` on the last line means it finished cleanly. Anything else means it
failed, and the lines above it say why.

Keeping several runs
^^^^^^^^^^^^^^^^^^^^

``>`` overwrites. To keep one log per run, put the date in the name:

.. code-block:: bash

   > gwis_import_wildfires_$(date +%Y%m%d_%H%M).log 2>&1

Alternatives to ``nohup``
^^^^^^^^^^^^^^^^^^^^^^^^^

``tmux`` (or ``screen``)
    Start ``tmux``, run the command in the foreground as if you were local, detach with
    ``Ctrl-b d`` and log out. ``tmux attach`` later puts you back in front of the live
    terminal, progress bar and all. It is more convenient when you want to watch, but it
    needs ``tmux`` installed on the server, and the output is kept only in the terminal
    scrollback unless you also redirect it.

``systemd-run``
    ``systemd-run --user --unit=gwis-import --working-directory=$HOME/GisFIRE
    .venv/bin/python -m ...`` runs it as a transient service. ``journalctl --user -u
    gwis-import`` shows the output and ``systemctl --user status gwis-import`` shows the
    exit status. It survives logout only if lingering is enabled for your user
    (``loginctl enable-linger``).

``nohup`` is what the import pages use because it is available everywhere and needs no
setup.

Against a remote database
-------------------------

The command runs on your machine and reads files from your disk, but the rows go to the
server's PostgreSQL. This is the right choice when the data is on your laptop and not
worth copying, or for the bindings and resyncs, which read no files at all. It is also
the slowest of the three. Every geometry goes over the network, both through
``ogr2ogr``'s staging load and through the application's own connection, and the import
stops if your machine sleeps or loses its connection.

The database settings come from the ``--db-*`` options instead of your local ``.env``.
Each option overrides the matching ``GISFIRE_DB_*`` variable, and options you leave out
still fall back to it (see :func:`src.apps.imports.common.resolve_database_settings`).

Through an SSH tunnel (recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The server's cluster does not need to accept network connections for this to work. An
SSH tunnel forwards a local port to the server's ``localhost``, so PostgreSQL sees an
ordinary local connection, the traffic is encrypted by SSH, and ``gisfire_user`` stays
local to the server as :ref:`pg-remote` recommends:

.. code-block:: bash

   ssh -N -L 15433:localhost:5433 user@server &     # local 15433 -> server's 5433
   read -rsp 'Database password: ' GISFIRE_DB_PASSWORD && export GISFIRE_DB_PASSWORD
   python3 -m src.apps.imports.wildfires.gwis.import_wildfires -d /path/to/zip/ \
       --db-host localhost --db-port 15433 \
       --db-name gisfire_db --db-user gisfire_user
   kill %1                                          # close the tunnel afterwards

- ``-N`` opens the tunnel without running a remote command; ``-L local:host:remote``
  makes ``localhost:15433`` here reach ``localhost:5433`` as seen *from the server*.
- The local port is ``15433`` rather than ``5433`` so that it cannot clash with a
  GisFIRE cluster on your own machine, which is itself on ``5433``. With the same
  number, ``ssh`` would fail to bind the port, or you would quietly import into your
  local database.
- ``ogr2ogr`` goes through the same tunnel. The application passes it the same host
  and port, so both connections reach the same server.

Directly
^^^^^^^^

If the server's cluster is configured for remote access (:ref:`pg-remote`, a
``hostssl`` rule in ``pg_hba.conf`` for the role and your network), skip the tunnel and
point at the server itself:

.. code-block:: bash

   python3 -m src.apps.imports.wildfires.gwis.import_wildfires -d /path/to/zip/ \
       --db-host server.example.org --db-port 5433 \
       --db-name gisfire_db --db-user gisfire_user

The role needs write access: the read-only ``gisfire_remoteuser`` meant for QGIS cannot
import anything.

The password
^^^^^^^^^^^^

There is a ``--db-password`` option, but avoid it. A password on the command line can be
read by every user on the machine through ``ps`` for as long as the import runs, and it
stays in your shell history. Pass it through the environment instead: the ``read -rsp``
line above prompts for it without echoing and exports it as ``GISFIRE_DB_PASSWORD``,
which the application reads, and it only lasts for that shell. The application in turn
hands it to ``ogr2ogr`` as ``PGPASSWORD`` rather than as an argument, for the same
reason.

To run a remote-database import unattended as well, combine it with the previous
section: start the tunnel and the ``nohup`` command in a ``tmux`` session on a machine
that stays on. It is usually simpler to copy the files to the server and use the SSH
variant.
