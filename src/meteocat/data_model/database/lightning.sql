-- lightning.sql


CREATE TABLE meteocat_lightning (
        id INTEGER NOT NULL,
        meteocat_id INTEGER NOT NULL,
        meteocat_peak_current FLOAT NOT NULL,
        meteocat_multiplicity INTEGER,
        meteocat_chi_squared FLOAT NOT NULL,
        meteocat_ellipse_major_axis FLOAT NOT NULL,
        meteocat_ellipse_minor_axis FLOAT NOT NULL,
        meteocat_ellipse_angle FLOAT NOT NULL,
        meteocat_number_of_sensors INTEGER NOT NULL,
        meteocat_hit_ground BOOLEAN NOT NULL,
        meteocat_municipality_code VARCHAR,
        x_4258 FLOAT NOT NULL,
        y_4258 FLOAT NOT NULL,
        geometry_4258 geometry(POINT,4258) NOT NULL,
        x_25831 FLOAT NOT NULL,
        y_25831 FLOAT NOT NULL,
        geometry_25831 geometry(POINT,25831) NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(id) REFERENCES lightning (id)

)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_lightning
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_lightning to gisfire_remoteuser;
