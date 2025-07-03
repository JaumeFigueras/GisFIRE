-- storm_cell_lightning_association.sql

CREATE TABLE storm_cell_lightning_association_table (
        storm_cell_id INTEGER NOT NULL,
        lightning_id INTEGER NOT NULL,
        PRIMARY KEY (storm_cell_id, lightning_id),
        FOREIGN KEY(storm_cell_id) REFERENCES storm_cell (id),
        FOREIGN KEY(lightning_id) REFERENCES lightning (id)
)

WITH (
  OIDS = FALSE
);
ALTER TABLE public.storm_cell_lightning_association_table
  OWNER TO gisfire_user
;
GRANT ALL on public.storm_cell_lightning_association_table to gisfire_remoteuser;

