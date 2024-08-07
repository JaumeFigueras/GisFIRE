-- user.sql

CREATE TABLE "user" (
        id SERIAL NOT NULL,
        username VARCHAR NOT NULL,
        token VARCHAR NOT NULL,
        is_admin BOOLEAN NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo_valid_until VARCHAR NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (username)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public."user"
  OWNER TO gisfire_user
;
GRANT ALL on public."user" to gisfire_remoteuser;