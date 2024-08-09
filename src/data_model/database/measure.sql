-- meteocat_measure.sql

CREATE TABLE measure (
        id VARCHAR NOT NULL,
        value FLOAT NOT NULL,
        type VARCHAR NOT NULL,
        data_provider_name VARCHAR NOT NULL,
        measure_date_time TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo_measure_date_time VARCHAR NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(data_provider_name) REFERENCES data_provider (name)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.measure
  OWNER TO gisfire_user
;
GRANT ALL on public.measure to gisfire_remoteuser;
