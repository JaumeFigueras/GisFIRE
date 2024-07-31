-- weather_station.sql

CREATE TABLE weather_station (
        id SERIAL NOT NULL,
        name VARCHAR NOT NULL,
        altitude FLOAT,
        type VARCHAR NOT NULL,
        data_provider_name VARCHAR NOT NULL,
        x_4326 FLOAT NOT NULL,
        y_4326 FLOAT NOT NULL,
        geometry_4326 geometry(POINT,4326) NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(data_provider_name) REFERENCES data_provider (name)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.weather_station
  OWNER TO gisfire_user
;
GRANT ALL on public.weather_station to gisfire_remoteuser;
