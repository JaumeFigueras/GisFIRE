-- meteocat_measure.sql

CREATE TYPE meteocat_measure_validity_category AS ENUM (' ', 'V', 'T');

CREATE TABLE meteocat_measure (
        meteocat_id VARCHAR NOT NULL,
        validity_state meteocat_measure_validity_category NOT NULL,
        time_base_category meteocat_variable_time_base_category NOT NULL,
        weather_station_id INTEGER NOT NULL,
        variable_id INTEGER NOT NULL,
        id VARCHAR NOT NULL,
        extreme_date_time TIMESTAMP WITH TIME ZONE,
        tzinfo_extreme_date_time VARCHAR,
        PRIMARY KEY (id),
        FOREIGN KEY(weather_station_id) REFERENCES weather_station (id),
        FOREIGN KEY(variable_id) REFERENCES variable (id),
        FOREIGN KEY(id) REFERENCES measure (id)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_measure
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_measure to gisfire_remoteuser;
