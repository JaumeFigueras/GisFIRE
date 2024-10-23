-- ogr2ogr -f PostgreSQL "postgresql://user:password@host:port/db" -t_srs EPSG:25831 -overwrite -lco GEOMETRY_NAME=geometry_25831 -nln catalunya dades-catalunya.gpkg catalunya

-- ALTER TABLE catalunya ADD geometry_4326 geometry(MULTIPOLYGON, 4326);
-- ALTER TABLE catalunya ADD geometry_4258 geometry(MULTIPOLYGON, 4258);
-- ALTER TABLE catalunya ADD geometry_25831 geometry(MULTIPOLYGON, 25831);

-- UPDATE catalunya SET geometry_4326 = ST_Transform(catalunya.geom, 4326);
-- UPDATE catalunya SET geometry_4258 = ST_Transform(catalunya.geom, 4258);
-- UPDATE catalunya SET geometry_25831 = ST_Transform(catalunya.geom, 25831);

ALTER TABLE catalunya DROP COLUMN geometry_43258;
ALTER TABLE catalunya DROP COLUMN geom;

 create or replace view lightnings_joined as
 select lightning.id,
    lightning.geometry_4326,
    lightning.date_time,
    meteocat_lightning.geometry_25831
   FROM lightning
     JOIN meteocat_lightning ON lightning.id = meteocat_lightning.id , catalunya WHERE ST_Contains(catalunya.geometry_25831, meteocat_lightning.geometry_25831);