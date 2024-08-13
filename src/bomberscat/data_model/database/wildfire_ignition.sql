-- wildfire_ignition.sql

CREATE TYPE bomberscat_validation_level_category AS ENUM ('NONE', 'CORRECTED', 'UNUSABLE', 'DISCARDED');

CREATE TABLE bomberscat_wildfire_ignition (
        x_25831 FLOAT NOT NULL,
        y_25831 FLOAT NOT NULL,
        geometry_25831 geometry(POINT,25831) NOT NULL,
        x_4258 FLOAT NOT NULL,
        y_4258 FLOAT NOT NULL,
        geometry_4258 geometry(POINT,4258) NOT NULL,
        id INTEGER NOT NULL,
        region VARCHAR NOT NULL,
        burned_surface FLOAT NOT NULL,
        validation_level bomberscat_validation_level_category NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(id) REFERENCES wildfire_ignition (id)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.bomberscat_wildfire_ignition
  OWNER TO gisfire_user
;
GRANT ALL on public.bomberscat_wildfire_ignition to gisfire_remoteuser;

