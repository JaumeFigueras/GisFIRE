-- database_init.sql
SET timezone='Europe/Madrid';

DO
$do$
BEGIN
	IF NOT EXISTS (
		SELECT FROM pg_catalog.pg_roles  -- SELECT list can be empty for this
    	WHERE rolname = 'gisfire_user') THEN
            CREATE ROLE gisfire_user WITH PASSWORD '1234';
            GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO gisfire_user;
   END IF;
END
$do$;

DO
$do$
BEGIN
   IF NOT EXISTS (
		SELECT FROM pg_catalog.pg_roles  -- SELECT list can be empty for this
    	WHERE rolname = 'gisfire_remoteuser') THEN
            CREATE ROLE gisfire_remoteuser WITH PASSWORD '1234';
            GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO gisfire_remoteuser;
   END IF;
END
$do$;

CREATE EXTENSION postgis;
CREATE EXTENSION hstore;

ALTER DATABASE test OWNER TO gisfire_user;
SET SESSION AUTHORIZATION 'gisfire_user';

