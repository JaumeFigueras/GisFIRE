-- lightning.sql

CREATE TABLE lightning (
        x_4326 FLOAT NOT NULL,
        y_4326 FLOAT NOT NULL,
        geometry_4326 geometry(POINT,4326) NOT NULL,
        id SERIAL NOT NULL,
        type VARCHAR NOT NULL,
        data_provider_name VARCHAR NOT NULL,
        date_time TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo VARCHAR NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
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

