PostgreSQL Database
===================

.. contents::
   :local:
   :depth: 2

Overview
--------

GisFIRE stores its data in a **PostgreSQL 15+** database with the **PostGIS** extension
enabled for spatial types. The models are mapped with SQLAlchemy and GeoAlchemy2, and
the geometry columns use PostGIS ``Geometry`` types.

GisFIRE runs in its **own PostgreSQL cluster**, not in the distribution's default one.
A cluster is a complete, independent server instance: its own data directory, its own
port, its own configuration files, its own log and its own set of users and databases.
Keeping GisFIRE in a dedicated cluster means the project can be tuned, stopped,
restarted, dumped, moved to another disk or deleted outright without touching any other
service on the machine, and a runaway import can never fill the system partition.

This page documents the whole sequence on a Linux server, from ``apt install`` to a
database with PostGIS enabled and a working ``.env``. The native geospatial libraries
that support PostGIS have their own page: :doc:`geospatial_libraries`.

The examples use the values of this project's ``.env.example``:

.. list-table::
   :header-rows: 1
   :widths: 28 32 40

   * - What
     - Example value
     - Notes
   * - PostgreSQL major version
     - ``17``
     - The version Debian 13 (trixie) ships. Any 15+ works.
   * - Cluster name
     - ``gisfire``
     - Distinct from the distribution's default ``main``.
   * - Cluster root directory
     - ``/home/postgresql-17``
     - One directory per major version, one sub-directory per cluster.
   * - Data directory (``PGDATA``)
     - ``/home/postgresql-17/gisfire``
     - Created by ``pg_createcluster``.
   * - Port
     - ``5433``
     - ``5432`` stays with the default cluster.
   * - Owner role
     - ``gisfire_user``
     - Owns the database; the one the application and Alembic use.
   * - Read-only role
     - ``gisfire_remoteuser``
     - Optional, for QGIS and other remote consumers.
   * - Database
     - ``gisfire_db``
     - UTF-8, owned by ``gisfire_user``; locale inherited from the cluster.

.. _pg-install:

1. Installing PostgreSQL and PostGIS
------------------------------------

From the distribution repositories
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

On Debian/Ubuntu the server, the client tools and the Debian cluster-management
wrappers come from three packages:

.. code-block:: bash

   sudo apt update
   sudo apt install postgresql postgresql-client postgresql-contrib

- ``postgresql`` — metapackage pulling the current major server (``postgresql-17``
  on Debian 13) and ``postgresql-common``, which provides ``pg_createcluster``,
  ``pg_lsclusters``, ``pg_ctlcluster`` and ``pg_dropcluster``.
- ``postgresql-client`` — ``psql``, ``createuser``, ``createdb``, ``pg_dump``, ...
- ``postgresql-contrib`` — the bundled extensions (``pg_trgm``, ``hstore``,
  ``fuzzystrmatch`` — the last one is needed by ``postgis_tiger_geocoder`` if you ever
  enable it).

Then PostGIS, which must match the server major version:

.. code-block:: bash

   sudo apt install postgresql-17-postgis-3 postgresql-17-postgis-3-scripts postgis

- ``postgresql-17-postgis-3`` — the PostGIS 3 extension **for PostgreSQL 17**. The
  version number in the package name is not cosmetic: an extension built for 17 cannot
  be loaded by a 16 cluster.
- ``postgresql-17-postgis-3-scripts`` — the SQL scripts ``CREATE EXTENSION`` runs.
- ``postgis`` — the command-line tools (``shp2pgsql``, ``pgsql2shp``,
  ``raster2pgsql``), useful for bulk-loading shapefiles outside the Python importers.

Add ``postgis-doc`` if you want the HTML reference installed locally.

.. note::

   Installing ``postgresql`` **automatically creates a default cluster** — ``main``,
   on port 5432, with its data in ``/var/lib/postgresql/17/main``. Leave it alone; the
   GisFIRE cluster is created next to it, and ``pg_lsclusters`` will list both.

From the PGDG repository (newer than the distribution)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When the server needs a PostgreSQL newer than the distribution's, use the official
PostgreSQL APT repository instead. It ships every supported major version in parallel,
with the same Debian cluster tooling:

.. code-block:: bash

   sudo apt install curl ca-certificates
   sudo install -d /usr/share/postgresql-common/pgdg
   sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
   echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
   https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        | sudo tee /etc/apt/sources.list.d/pgdg.list
   sudo apt update
   sudo apt install postgresql-17 postgresql-client-17 postgresql-17-postgis-3

Verifying the installation
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   psql --version                 # client version
   pg_lsclusters                  # every cluster known to the machine
   ls /usr/lib/postgresql         # the major versions installed side by side

.. _pg-cluster:

2. Creating a dedicated cluster
-------------------------------

Directory convention
^^^^^^^^^^^^^^^^^^^^

**Every cluster gets its own root directory, named after the major version**, with one
sub-directory per cluster:

.. code-block:: text

   /home/postgresql-17/            <- root for all PostgreSQL 17 clusters
   ├── gisfire/                    <- PGDATA of the cluster "gisfire"
   │   └── gisfire.log             <- its log file, kept with the cluster
   └── <other-cluster>/            <- a second 17 cluster, if ever needed

``/home`` is used rather than ``/var/lib/postgresql`` because on most of our machines
``/home`` is the large, separately mounted partition: database growth then cannot fill
the root filesystem, and the whole cluster can be moved by moving one directory. A
major upgrade creates ``/home/postgresql-18`` beside it, so both versions can coexist
while the data is migrated.

Prepare the root directory — it must exist and belong to the ``postgres`` system user
before the cluster is created (``pg_createcluster`` creates the data directory itself,
with the strict permissions the server requires):

.. code-block:: bash

   sudo mkdir -p /home/postgresql-17
   sudo chown postgres:postgres /home/postgresql-17
   sudo chmod 750 /home/postgresql-17

Creating the cluster
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   sudo pg_createcluster \
       -d /home/postgresql-17/gisfire \
       -l /home/postgresql-17/gisfire/gisfire.log \
       -p 5433 \
       --start --start-conf auto \
       17 gisfire

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - Argument
     - Meaning
   * - ``17 gisfire``
     - Major version and cluster name — they go **last**, after the options.
       Together they identify the cluster in every other ``pg_*cluster`` command
       and in the systemd unit ``postgresql@17-gisfire``.
   * - ``-d`` (``--datadir``)
     - Where the data lives, instead of the default
       ``/var/lib/postgresql/17/gisfire``.
   * - ``-l`` (``--logfile``)
     - Keeps the cluster's log inside the cluster directory instead of in
       ``/var/log/postgresql``, so the whole cluster — data and log — is one
       self-contained directory.
   * - ``-p`` (``--port``)
     - Must be free and different from every other cluster's (``5432`` is taken by
       ``main``).
   * - ``--start``
     - Starts the cluster immediately after creating it.
   * - ``--start-conf auto``
     - Writes ``auto`` to ``start.conf``, so the cluster also comes back up at
       boot. The other values are ``manual`` and ``disabled``.

Encoding and locale are deliberately **not** passed: the cluster inherits the
server's defaults, which is what we want on machines whose locale is already set
the way the administrator intends. Confirm what was inherited once the cluster is
up — the datasets carry accented and non-Latin text, so the encoding has to be
``UTF8``:

.. code-block:: bash

   sudo -u postgres psql --port=5433 -c "SHOW server_encoding;" -c "SHOW lc_collate;"

If a server default ever turns out not to be UTF-8, that is the moment to create
the cluster with an explicit ``--locale``/``--encoding`` instead.

Check the result:

.. code-block:: bash

   pg_lsclusters

.. code-block:: text

   Ver Cluster Port Status Owner    Data directory              Log file
   17  gisfire 5433 online postgres /home/postgresql-17/gisfire /home/postgresql-17/gisfire/gisfire.log
   17  main    5432 online postgres /var/lib/postgresql/17/main /var/log/postgresql/postgresql-17-main.log

Without the Debian wrappers
^^^^^^^^^^^^^^^^^^^^^^^^^^^

``pg_createcluster`` is Debian/Ubuntu-specific. On other distributions the same thing
is done with ``initdb`` and ``pg_ctl``, run as the ``postgres`` user:

.. code-block:: bash

   sudo mkdir -p /home/postgresql-17/gisfire
   sudo chown postgres:postgres /home/postgresql-17/gisfire
   sudo chmod 700 /home/postgresql-17/gisfire
   sudo -u postgres /usr/lib/postgresql/17/bin/initdb -D /home/postgresql-17/gisfire
   sudo -u postgres /usr/lib/postgresql/17/bin/pg_ctl \
        -D /home/postgresql-17/gisfire -o "-p 5433" \
        -l /home/postgresql-17/gisfire/gisfire.log start

``initdb`` likewise takes its encoding and locale from the environment it runs in.
The difference from the Debian route is where the configuration ends up: with
``initdb`` the files stay inside the data directory, with ``pg_createcluster`` they
live in ``/etc/postgresql/17/gisfire/``. There is no ``start.conf`` either — boot
behaviour is whatever service unit you write.

Managing the cluster
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   sudo pg_ctlcluster 17 gisfire start|stop|restart|reload
   sudo systemctl start postgresql@17-gisfire        # equivalent, via systemd
   sudo systemctl status postgresql@17-gisfire

- Configuration: ``/etc/postgresql/17/gisfire/postgresql.conf`` and ``pg_hba.conf``.
- Autostart at boot: the ``start.conf`` file in that directory, written by
  ``--start-conf`` above — ``auto``, ``manual`` or ``disabled``. It can be changed
  later by editing the file.
- Removing it completely (**destroys the data**):
  ``sudo pg_dropcluster 17 gisfire --stop``.
- Backups are per cluster too:
  ``pg_dump -h localhost -p 5433 -U gisfire_user -Fc gisfire_db > gisfire_db.dump``.

.. warning::

   If the cluster refuses to start with a permission error on a path under ``/home``,
   check whether the service unit is sandboxed (``ProtectHome=``). Debian's
   ``postgresql@.service`` is not, but some distributions ship one that is; the fix is
   a drop-in with ``ProtectHome=false``. SELinux-based systems additionally need the
   data directory labelled (``semanage fcontext``/``restorecon``).

.. _pg-roles:

3. Creating the roles
---------------------

Right after ``initdb`` the only role that exists is the superuser ``postgres``, and the
only way in is the ``postgres`` **system** account (the cluster authenticates local
connections by operating-system user). So every administrative step below starts by
becoming that user:

.. code-block:: bash

   sudo -i -u postgres

``-i`` starts a **login** shell: it reads ``postgres``'s own profile and lands in
``postgres``'s home directory with a clean environment, which is what you want for
administrative work (``sudo -su postgres`` also works, but keeps your environment and
your current directory, so a stray ``PGPORT``/``PGDATABASE`` or a relative path to an
SQL file can behave differently from what you expect). Leave it again with ``exit``.

.. important::

   Inside that shell, **always pass the port**. Without ``--port=5433`` the client
   tools connect to the default cluster on 5432 and the role or database is created in
   the wrong server.

Create the application role — the one that owns the database and that the backend, the
importers and Alembic connect as. It needs no special attributes: not a superuser, and
allowed neither to create databases nor roles.

.. code-block:: bash

   createuser --port=5433 --pwprompt \
              --no-superuser --no-createdb --no-createrole gisfire_user

The three ``--no-*`` flags are written out for the record only: they are already
``createuser``'s defaults (as are ``LOGIN`` and ``INHERIT``), and it never asks about
attributes unless ``--interactive`` is given. The short form is the same command:

.. code-block:: bash

   createuser -p 5433 -P gisfire_user

``--pwprompt`` (``-P``) asks for the password twice and stores it hashed
(SCRAM-SHA-256). Use a long random one — it goes into ``.env`` as
``GISFIRE_DB_PASSWORD`` and is never typed by hand:

.. code-block:: bash

   openssl rand -base64 48

The same thing in SQL, if you prefer ``psql`` — but note that this form puts the
plaintext password on the command line, where it is visible to ``ps`` and is kept in
the shell history and in ``~/.psql_history``; ``--pwprompt`` avoids all three:

.. code-block:: bash

   psql --port=5433 -c "CREATE ROLE gisfire_user LOGIN PASSWORD 'the-password';"

Optionally create a second, read-only role for QGIS and other remote consumers, so that
nothing outside the project can write to the database:

.. code-block:: bash

   createuser --port=5433 --pwprompt \
              --no-superuser --no-createdb --no-createrole gisfire_remoteuser

Its grants can only be given once the database exists and the schema has been
migrated — see :ref:`pg-readonly-grants`.

.. _pg-database:

4. Creating the database
------------------------

Still as the ``postgres`` user:

.. code-block:: bash

   sudo -i -u postgres
   createdb --port=5433 --owner=gisfire_user --encoding=UTF8 gisfire_db

short form, and in SQL:

.. code-block:: bash

   createdb -p 5433 -E UTF8 -O gisfire_user gisfire_db

.. code-block:: sql

   CREATE DATABASE gisfire_db OWNER gisfire_user ENCODING 'UTF8';

The locale is still left to the cluster, but ``--encoding=UTF8`` is worth stating.
It is not a conversion — a new database is cloned from ``template1`` and cannot have a
different encoding from it — it is an **assertion**: on a cluster whose template is
LATIN1 or SQL_ASCII the command fails with a clear error instead of quietly giving
GisFIRE a database that mangles accents. If that ever happens, create the database from
``template0`` with an explicit locale rather than dropping the flag.

Making ``gisfire_user`` the **owner** matters: from PostgreSQL 15 on, the ``public``
schema is owned by ``pg_database_owner`` and ordinary roles no longer get ``CREATE`` on
it. As the owner, ``gisfire_user`` can create tables, so ``alembic upgrade head`` works
without extra grants. A non-owner role would additionally need:

.. code-block:: sql

   GRANT ALL ON SCHEMA public TO gisfire_user;

Check it is there:

.. code-block:: bash

   psql --port=5433 -l

.. _pg-postgis:

5. Enabling PostGIS in the database
-----------------------------------

PostGIS is installed on the machine but not in the database; each database that needs
spatial types must have the extension created in it. This requires superuser rights
(PostGIS is not a *trusted* extension), so it is again done as ``postgres``:

.. code-block:: bash

   sudo -i -u postgres
   psql --port=5433 --dbname=gisfire_db

.. code-block:: sql

   CREATE EXTENSION IF NOT EXISTS postgis;

That single statement installs the geometry and geography types, the several hundred
spatial functions and the ``spatial_ref_sys`` table of CRS definitions, all in the
``public`` schema. GisFIRE needs nothing else; the optional companions are only worth
adding if a specific dataset requires them:

.. code-block:: sql

   CREATE EXTENSION postgis_raster;     -- raster type (fuel maps, burnt-area rasters)
   CREATE EXTENSION postgis_topology;   -- topology model, own "topology" schema
   CREATE EXTENSION fuzzystrmatch;      -- prerequisite of the geocoder below
   CREATE EXTENSION postgis_tiger_geocoder;

Verify:

.. code-block:: sql

   SELECT postgis_full_version();

.. code-block:: text

   POSTGIS="3.5.2" [EXTENSION] PGSQL="170" GEOS="3.13.1-CAPI-1.19.2"
   PROJ="9.6.0 ..." LIBXML="2.9.14" LIBJSON="0.18" LIBPROTOBUF="1.5.1" ...

The line also tells you which GEOS and PROJ the server is linked against — see
:doc:`geospatial_libraries` for what those are and what else the server should have.

.. note::

   Install PostGIS **in the** ``public`` **schema** (the default). The ORM models and
   the migrations do not qualify type names, so a PostGIS in another schema would only
   work with a modified ``search_path``.

The extension objects are owned by ``postgres``, not by ``gisfire_user``; this is
normal and read access is public, so the application role can use the types and
functions and read ``spatial_ref_sys`` without any grant. Two practical consequences:
``DROP EXTENSION`` needs a superuser, and so does adding a custom CRS row to
``spatial_ref_sys``.

.. _pg-readonly-grants:

Read-only grants
^^^^^^^^^^^^^^^^

Once the schema has been created (``alembic upgrade head``, see
:doc:`database_migrations`), grant the remote role read access. Run this as
``gisfire_user``, the owner of the tables:

.. code-block:: sql

   GRANT CONNECT ON DATABASE gisfire_db TO gisfire_remoteuser;
   GRANT USAGE ON SCHEMA public TO gisfire_remoteuser;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO gisfire_remoteuser;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO gisfire_remoteuser;

The last statement is what keeps the role useful: without it, every table and ``v_*``
view created by a later migration would be invisible to it.

.. _pg-connect:

6. Pointing GisFIRE at the cluster
----------------------------------

Copy ``.env.example`` to ``.env`` and fill in the values used above — note the
**port**, which is the part most easily forgotten:

.. code-block:: bash

   GISFIRE_DB_HOST=localhost
   GISFIRE_DB_PORT=5433
   GISFIRE_DB_NAME=gisfire_db
   GISFIRE_DB_USER=gisfire_user
   GISFIRE_DB_PASSWORD=<the password from step 3>

Check the whole chain from a normal user account, over TCP, exactly as the application
connects:

.. code-block:: bash

   psql -h localhost -p 5433 -U gisfire_user -d gisfire_db -c "SELECT postgis_version();"

Then create the schema:

.. code-block:: bash

   make migrate          # alembic upgrade head

See :doc:`configuration` for the full list of variables and
:doc:`database_migrations` for the migration workflow.

.. _pg-remote:

7. Remote access (optional)
---------------------------

A freshly created cluster only listens on ``localhost`` and the Unix socket. To let
QGIS or another host connect, edit ``/etc/postgresql/17/gisfire/postgresql.conf``:

.. code-block:: ini

   listen_addresses = '*'          # or a specific interface address
   port = 5433
   password_encryption = scram-sha-256

and add a rule to ``/etc/postgresql/17/gisfire/pg_hba.conf`` — as narrow as possible,
one line per role/network, TLS enforced with ``hostssl``:

.. code-block:: text

   # TYPE     DATABASE    USER                 ADDRESS          METHOD
   hostssl    gisfire_db  gisfire_remoteuser   10.0.0.0/24      scram-sha-256

Reload (``pg_hba.conf`` does not need a restart) and open the port in the firewall:

.. code-block:: bash

   sudo pg_ctlcluster 17 gisfire reload
   sudo ufw allow from 10.0.0.0/24 to any port 5433 proto tcp

.. warning::

   ``listen_addresses = '*'`` with a permissive ``pg_hba.conf`` exposes the database to
   the whole network. Prefer restricting by CIDR, using the read-only role for external
   consumers, and keeping ``gisfire_user`` local to the server.

.. _pg-tests:

8. The test database
--------------------

None of the above is needed to run the test suite: ``pytest-postgresql`` starts a
throwaway cluster of its own for the run, ``test/conftest.py`` executes
``CREATE EXTENSION IF NOT EXISTS postgis`` in it and builds the schema with
``Base.metadata.create_all()``. The permanent GisFIRE cluster is never opened, never
migrated and never truncated by the tests.

What the test suite does need from this page is the **software**: ``initdb`` and
``pg_ctl`` on ``PATH`` (from ``postgresql-17``) and a PostGIS matching that same
version, because the ephemeral cluster is created with those binaries. See
:doc:`../testing`.

Quick reference
---------------

.. code-block:: bash

   # install
   sudo apt install postgresql postgresql-client postgresql-contrib
   sudo apt install postgresql-17-postgis-3 postgresql-17-postgis-3-scripts postgis

   # cluster
   sudo mkdir -p /home/postgresql-17 && sudo chown postgres:postgres /home/postgresql-17
   sudo pg_createcluster -d /home/postgresql-17/gisfire \
        -l /home/postgresql-17/gisfire/gisfire.log -p 5433 \
        --start --start-conf auto 17 gisfire

   # roles, database, extension
   sudo -i -u postgres
   createuser --port=5433 --pwprompt --no-superuser --no-createdb --no-createrole gisfire_user
   createdb   --port=5433 --owner=gisfire_user --encoding=UTF8 gisfire_db
   psql       --port=5433 -d gisfire_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
   exit

   # application
   cp .env.example .env && $EDITOR .env      # host/port/name/user/password
   make migrate
