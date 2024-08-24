-- meteocat_variable.sql

CREATE TYPE meteocat_variable_category AS ENUM ('DAT', 'AUX', 'CMV');

CREATE TABLE meteocat_variable (
        id INTEGER NOT NULL,
        code INTEGER NOT NULL,
        unit VARCHAR NOT NULL,
        acronym VARCHAR NOT NULL,
        category meteocat_variable_category NOT NULL,
        decimal_positions INTEGER NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(id) REFERENCES variable (id),
        UNIQUE (code)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.meteocat_variable
  OWNER TO gisfire_user
;
GRANT ALL on public.meteocat_variable to gisfire_remoteuser;
CREATE INDEX meteocat_variable_code_idx ON meteocat_variable (code);
