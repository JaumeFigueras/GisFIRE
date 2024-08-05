-- variable.sql

CREATE TABLE variable (
        id SERIAL NOT NULL,
        name VARCHAR NOT NULL,
        type VARCHAR NOT NULL,
        data_provider_name VARCHAR NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(data_provider_name) REFERENCES data_provider (name)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.variable
  OWNER TO gisfire_user
;
GRANT ALL on public.variable to gisfire_remoteuser;
