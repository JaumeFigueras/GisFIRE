-- user.sql

CREATE TYPE httpmethods AS ENUM ('GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH');

CREATE TABLE user_access (
        id SERIAL NOT NULL,
        ip INET NOT NULL,
        url VARCHAR NOT NULL,
        method httpmethods NOT NULL,
        params HSTORE,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        user_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES "user" (id)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.user_access
  OWNER TO gisfire_user
;
GRANT ALL on public.user_access to gisfire_remoteuser;
