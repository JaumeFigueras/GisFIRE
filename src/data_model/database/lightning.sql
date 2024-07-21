-- lightning.sql

CREATE TABLE lightning (
        id SERIAL NOT NULL,
        date TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo VARCHAR NOT NULL,
        latitude_wgs84 FLOAT NOT NULL,
        longitude_wgs84 FLOAT NOT NULL,
        geom_wgs84 geometry(POINT,4326),
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        type VARCHAR NOT NULL,
        data_provider_name VARCHAR NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(data_provider_name) REFERENCES data_provider (name)
)
WITH (
  OIDS = FALSE
);
ALTER TABLE public.lightning
  OWNER TO gisfire_user
;
GRANT ALL on public.lightning to gisfire_remoteuser;

