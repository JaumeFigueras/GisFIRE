-- meteocat_weather_station_state.sql

CREATE TABLE meteocat_association_station_variable_state (
        meteocat_weather_station_id INTEGER NOT NULL,
        meteocat_variable_id INTEGER NOT NULL,
        meteocat_variable_state_id INTEGER NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (meteocat_weather_station_id, meteocat_variable_id, meteocat_variable_state_id),
        FOREIGN KEY(meteocat_weather_station_id) REFERENCES meteocat_weather_station (id),
        FOREIGN KEY(meteocat_variable_id) REFERENCES meteocat_variable (id),
        FOREIGN KEY(meteocat_variable_state_id) REFERENCES meteocat_variable_state (id)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_association_station_variable_state
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_association_station_variable_state to gisfire_remoteuser;

CREATE TABLE meteocat_association_station_variable_time_base (
        meteocat_weather_station_id INTEGER NOT NULL,
        meteocat_variable_id INTEGER NOT NULL,
        meteocat_variable_time_base_id INTEGER NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (meteocat_weather_station_id, meteocat_variable_id, meteocat_variable_time_base_id),
        FOREIGN KEY(meteocat_weather_station_id) REFERENCES meteocat_weather_station (id),
        FOREIGN KEY(meteocat_variable_id) REFERENCES meteocat_variable (id),
        FOREIGN KEY(meteocat_variable_time_base_id) REFERENCES meteocat_variable_time_base (id)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_association_station_variable_time_base
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_association_station_variable_time_base to gisfire_remoteuser;
