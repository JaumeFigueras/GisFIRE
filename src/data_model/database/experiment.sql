-- experiment.sql

CREATE TABLE experiment (
        name VARCHAR NOT NULL,
        params HSTORE NOT NULL,
        results HSTORE NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (name, params)
)
WITH (
  OIDS = FALSE
);
ALTER TABLE public.experiment
  OWNER TO gisfire_user
;
GRANT ALL on public.experiment to gisfire_remoteuser;
