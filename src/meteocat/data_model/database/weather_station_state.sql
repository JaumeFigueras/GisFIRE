-- meteocat_weather_station_state.sql

CREATE TABLE meteocat_weather_station_state (
        meteocat_weather_station_id INTEGER NOT NULL,
        code meteocat_state_category NOT NULL,
        valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo_valid_from VARCHAR NOT NULL,
        valid_until TIMESTAMP WITH TIME ZONE,
        tzinfo_valid_until VARCHAR,
        id SERIAL NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(meteocat_weather_station_id) REFERENCES meteocat_weather_station (id)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_weather_station_state
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_weather_station_state to gisfire_remoteuser;
