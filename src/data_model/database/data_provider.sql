-- data_provider.sql

CREATE TABLE data_provider (
        name VARCHAR NOT NULL,
        description VARCHAR NOT NULL,
        url VARCHAR NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (name)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.data_provider
  OWNER TO gisfire_user
;
GRANT ALL on public.data_provider to gisfire_remoteuser;