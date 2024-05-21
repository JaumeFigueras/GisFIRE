CREATE TABLE request (
        uri VARCHAR NOT NULL,
        params HSTORE NOT NULL,
        request_result INTEGER NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        data_provider_name VARCHAR NOT NULL,
        PRIMARY KEY (uri, params),
        FOREIGN KEY(data_provider_name) REFERENCES data_provider (name)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.asset
  OWNER TO gisfire_user
;
GRANT ALL on public.asset to gisfire_remoteuser;