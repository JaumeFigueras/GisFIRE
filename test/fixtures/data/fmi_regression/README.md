# FMI regression day: 2018-07-03

The public regression test of Cellsearch (`test_regression_fmi_2018_07_03` in
`test/apps/thunderstorms/test_build_thunderstorms.py`). The strokes can be
published (CC BY 4.0), so the files are committed and the test always runs.

| File | What it is |
|------|------------|
| `fmi_lightning_2018-07-03.csv` | FMI's 3,178 strokes of 2018-07-02 23:00 to 2018-07-04 00:00 UTC, as the downloader wrote them |
| `cellsearch_2018-07-03_expected.json` | What Cellsearch stores for 2018-07-03, one run per value of C |
| `freeze_cellsearch_2018-07-03.py` | Writes the JSON (and a GeoPackage for QGIS) from an empty scratch database |

## The strokes

Cut from `fmi_lightning_2018-07.csv.gz`, downloaded on 2026-11-14 with
`src/apps/download/lightnings/finland_fmi/download_lightnings.py`: every value
and the row order exactly as the service sent them. The hour before the day (109
strokes) is included because a storm was going on and the run's look-back reads
it, as it would in gisfire_db; the runs cover 2018-07-03 only (3,069 strokes,
2,488 flashes). They read its ground strokes only, the builder's default: 1,481
strokes in 900 flashes.

Why this day: about the size of MeteoCat's 2020-07-13 (2,947 strokes), three
quarters of it over Finland, and it exercises most of what the builder does — a
night storm running into the day (`activity_before_start`), a quiet gap of four
hours (the run is cut into pieces), evening storms in Lapland and in southern
Finland at once, intra-cloud strokes (52 %), 113 strokes located 10 km or worse
(discarded by E_max), and many strokes sharing a second.

The test loads it through the FMI importer, so the stroke ids follow the
importer's content order. That order is what makes the result independent of
the order a download returns: with the file's own order, a shuffled copy of this
day gives different cells (checked on 2026-11-14), and
`test_the_fmi_regression_does_not_depend_on_the_order_of_the_file` keeps it so.

## The expected result

Frozen on 2026-11-15 with `gisfire_algorithms` 0.1.0 and the default parameters
of then, N_min = 5 included (the default is 10 since 2026-11-21; the test and
the freeze script pass 5), in EPSG:3067, for C = off, 10, 15, 25, 50, 100 and
200 min·km, over the **ground strokes only** (`lightning_filter`
`{"cloud_to_ground": true}`, recorded in the JSON). **Awaiting Jaume's check in QGIS**, on the GeoPackage of the seven
runs written by the freeze script (`plans/fmi_cellsearch_2018-07-03_ground.gpkg`,
local). The previous reference, over all strokes, was checked on 2026-11-14.

To regenerate after a deliberate change of output (an algorithm's, with a bump
of `gisfire_algorithms.__version__`, or the builder's defaults'), create an
empty database, migrate it and run

```bash
GISFIRE_DB_NAME=scratch ... alembic upgrade head
python3 test/fixtures/data/fmi_regression/freeze_cellsearch_2018-07-03.py \
    --db-url postgresql+psycopg://user@host:port/scratch --gpkg /tmp/check.gpkg
```

then check the runs in QGIS and commit the new JSON.

## Licence

Source: Finnish Meteorological Institute (FMI), open data, CC BY 4.0
(https://en.ilmatieteenlaitos.fi/open-data-licence). The strokes are unmodified;
the expected result is derived from them.
