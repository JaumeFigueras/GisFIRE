-- meteocat_weather_station_state.sql

CREATE TYPE meteocat_weather_station_state_category AS ENUM ('ACTIVE', 'DISMANTLED', 'REPAIR');

CREATE TABLE meteocat_weather_station_state (
        code meteocat_weather_station_state_category NOT NULL,
        weather_station_id INTEGER,
        valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo_valid_from VARCHAR NOT NULL,
        valid_until TIMESTAMP WITH TIME ZONE,
        tzinfo_valid_until VARCHAR,
        id SERIAL NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(weather_station_id) REFERENCES weather_station (id)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_weather_station_state
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_weather_station_state to gisfire_remoteuser;
