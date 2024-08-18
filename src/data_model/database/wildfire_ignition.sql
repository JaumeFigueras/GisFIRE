-- wildfire_ignition.sql

CREATE TYPE wildfire_ignition_category AS ENUM ('LIGHTNING', 'AGRICOLE_BURNING', 'PASTURE_BURNING',
    'FORESTRY_ACTIVITIES', 'BONFIRE', 'SMOKERS', 'GARBAGE_BURNING', 'LANDFILL', 'STUBBLE_BURNING', 'OTHER_NEGLIGENCE',
    'RAILWAY', 'ELECTRIC_LINES', 'ENGINES_OR_MACHINES', 'MILITARY_MANEUVERS', 'OTHER_ACCIDENTS', 'INTENTIONAL',
    'UNKNOWN', 'REKINDLED_WILDFIRE');

CREATE TABLE wildfire_ignition (
        x_4326 FLOAT NOT NULL,
        y_4326 FLOAT NOT NULL,
        geometry_4326 geometry(POINT,4326) NOT NULL,
        start_date_time TIMESTAMP WITH TIME ZONE NOT NULL,
        tzinfo_start_date_time VARCHAR NOT NULL,
        id SERIAL NOT NULL,
        name VARCHAR NOT NULL,
        ignition_cause wildfire_ignition_category NOT NULL,
        type VARCHAR NOT NULL,
        data_provider_name VARCHAR NOT NULL,
        ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(data_provider_name) REFERENCES data_provider (name)
)
WITH (
  OIDS = FALSE
)
;
ALTER TABLE public.wildfire_ignition
  OWNER TO gisfire_user
;
GRANT ALL on public.wildfire_ignition to gisfire_remoteuser;

