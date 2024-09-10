-- ALTER TABLE catalunya ADD geometry_4326 geometry(MULTIPOLYGON, 4326);
-- ALTER TABLE catalunya ADD geometry_4258 geometry(MULTIPOLYGON, 4258);
-- ALTER TABLE catalunya ADD geometry_25831 geometry(MULTIPOLYGON, 25831);

-- UPDATE catalunya SET geometry_4326 = ST_Transform(catalunya.geom, 4326);
-- UPDATE catalunya SET geometry_4258 = ST_Transform(catalunya.geom, 4258);
-- UPDATE catalunya SET geometry_25831 = ST_Transform(catalunya.geom, 25831);

ALTER TABLE catalunya DROP COLUMN geometry_43258;
ALTER TABLE catalunya DROP COLUMN geom;