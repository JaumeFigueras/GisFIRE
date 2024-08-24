-- meteocat_weather_station.sql

CREATE TYPE meteocat_weather_station_category AS ENUM ('AUTO', 'OTHER');

CREATE TABLE meteocat_weather_station (
        id INTEGER NOT NULL,
        meteocat_code VARCHAR NOT NULL,
        meteocat_type meteocat_weather_station_category NOT NULL,
        meteocat_placement VARCHAR NOT NULL,
        meteocat_municipality_code VARCHAR NOT NULL,
        meteocat_municipality_name VARCHAR NOT NULL,
        meteocat_county_code VARCHAR NOT NULL,
        meteocat_county_name VARCHAR NOT NULL,
        meteocat_province_code VARCHAR NOT NULL,
        meteocat_province_name VARCHAR NOT NULL,
        meteocat_network_code VARCHAR NOT NULL,
        meteocat_network_name VARCHAR NOT NULL,
        x_4258 FLOAT NOT NULL,
        y_4258 FLOAT NOT NULL,
        geometry_4258 geometry(POINT,4258) NOT NULL,
        x_25831 FLOAT NOT NULL,
        y_25831 FLOAT NOT NULL,
        geometry_25831 geometry(POINT,25831) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(id) REFERENCES weather_station (id),
        UNIQUE (meteocat_code)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_weather_station
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_weather_station to gisfire_remoteuser;
CREATE INDEX meteocat_weather_station_code_idx ON meteocat_weather_station (meteocat_code);
