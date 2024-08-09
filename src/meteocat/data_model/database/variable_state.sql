-- meteocat_variable_state.sql

CREATE TYPE meteocat_variable_state_category AS ENUM ('ACTIVE', 'DISMANTLED', 'REPAIR');

CREATE TABLE meteocat_variable_state (
        code meteocat_variable_state_category NOT NULL,
        meteocat_weather_station_id INTEGER NOT NULL,
        meteocat_variable_id INTEGER NOT NULL,
        valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo_valid_from VARCHAR NOT NULL,
        valid_until TIMESTAMP WITH TIME ZONE,
        tzinfo_valid_until VARCHAR,
        id SERIAL NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(meteocat_weather_station_id) REFERENCES meteocat_weather_station (id),
        FOREIGN KEY(meteocat_variable_id) REFERENCES meteocat_variable (id)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_variable_state
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_variable_state to gisfire_remoteuser;
