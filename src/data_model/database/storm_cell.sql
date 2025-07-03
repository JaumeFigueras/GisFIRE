-- storm_cell.sql

CREATE TABLE storm_cell (
        id SERIAL NOT NULL,
        algorithm_used VARCHAR NOT NULL,
        algorithm_parameter_time FLOAT DEFAULT NULL,
        algorithm_parameter_distance FLOAT DEFAULT NULL,
        type VARCHAR NOT NULL,
        data_provider_name VARCHAR NOT NULL,
        date_time_start TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo_date_time_start VARCHAR NOT NULL,
        date_time_end TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo_date_time_end VARCHAR NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(data_provider_name) REFERENCES data_provider (name)
)
WITH (
  OIDS = FALSE
);
ALTER TABLE public.storm_cell
  OWNER TO gisfire_user
;
GRANT ALL on public.storm_cell to gisfire_remoteuser;

