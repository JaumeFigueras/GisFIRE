-- meteocat_measure.sql

CREATE TYPE meteocat_measure_validity_category AS ENUM ('NO_DATA', 'PENDING', 'VALID', 'VALIDATING');

CREATE TABLE meteocat_measure (
        meteocat_id VARCHAR NOT NULL,
        validity_state meteocat_measure_validity_category NOT NULL,
        time_base_category meteocat_variable_time_base_category NOT NULL,
        meteocat_weather_station_id INTEGER NOT NULL,
        meteocat_variable_id INTEGER NOT NULL,
        extreme_date_time TIMESTAMP WITH TIME ZONE,
        tzinfo_extreme_date_time VARCHAR,
        id INTEGER NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(meteocat_weather_station_id) REFERENCES meteocat_weather_station (id),
        FOREIGN KEY(meteocat_variable_id) REFERENCES meteocat_variable (id),
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

CREATE INDEX meteocat_weather_station_id_idx ON meteocat_measure (meteocat_weather_station_id);
CREATE INDEX meteocat_variable_id_idx ON meteocat_measure (meteocat_variable_id);