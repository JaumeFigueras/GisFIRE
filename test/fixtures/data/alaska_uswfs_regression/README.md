# Alaska regression day: 2019-06-30

The public regression test of Cellsearch on the Alaska network
(`test_regression_alaska_2019_06_30` in
`test/apps/thunderstorms/test_build_thunderstorms.py`). The strokes are public
domain, so, as with FMI's day, the files are committed and the test always runs.

- `alaska_uswfs_lightning_2019-06-30.txt`: the Alaska network's 5,892 strokes of
  2019-06-30 11:00 to 2019-07-01 12:00 UTC, cut verbatim from the release.
- `cellsearch_2019-06-30_expected.json`: what Cellsearch stores for the window,
  one run per value of C.
- `freeze_cellsearch_2019-06-30.py`: writes the JSON (and a GeoPackage for QGIS)
  from an empty scratch database.

## The strokes

Lines 1,222,989 to 1,228,880 of `Historical_Lightning_2012_2026_TOA_WGS84.txt`,
with its first line (byte-order mark and header) and its line endings. That is
the strokes file of the U.S. Wildland Fire Service release
`Historical_Lightning_2012_forward_as_txt.zip` of 2026-11-06, downloaded on
2026-11-13 from <https://fire.ak.blm.gov/predsvcs/maps.php>. Every byte of those
lines is as published. The lines before and after lie outside the cut. The test
reads the file as the release's extracted `.txt`, so the importer warns that no
FGDC metadata vouches for it.

**The window is 2019-06-30 12:00 to 2019-07-01 12:00 UTC**, 04:00 to 04:00 in
Alaska (AKDT, UTC-8). A UTC day would cut the storms in two: Alaska's thunderstorms
peak in the local afternoon and evening, around midnight UTC. The hour before
the window (118 strokes) is in the file because the run's look-back reads it, as it
would in gisfire_db.

In the window, as the importer stores them: 5,774 strokes (170 cloud strokes) in
3,764 flashes, grouped by the importer (the release has no flashes); 148 strokes
share their millisecond with another.

Why this day:

- **Busy, with several storms.** It is about twice FMI's day and is spread
  from 55° N to 71° N and from 160° W to 107° W, mostly along the Alaska-Yukon
  border. Each run keeps 120 to 129 cells, the largest of 161 to 236 flashes.
- **Errors of an Alaska kind.** 330 flashes (8.8 %) have their best location
  error at 10 km or worse and are discarded by E_max.
  - From 11:20 to 16:07 UTC the network published a semi-major axis of 0 for
    every stroke: 77 strokes, stored with an unknown error.
  - 34 of them are in the window, in 30 flashes with no stroke of known error.
    Every E_max discards those 30, which the test checks with an E_max of
    10,000 km.
- **The opposite edges to FMI's day.** The window starts quiet (no activity
  before it) and ends with storms still going: 5 or 6 cells are open at its end.

The ids follow the importer's content order, not the file's, and
`test_the_alaska_regression_does_not_depend_on_the_order_of_the_file` checks
that a shuffled copy gives the same result.

## The expected result

Frozen on 2026-11-15 with `gisfire_algorithms` 0.1.0 and the default parameters
in EPSG:3338 (NAD83 / Alaska Albers), for C = off, 10, 15, 25, 50, 100 and 200
min·km, and **checked by Jaume in QGIS on 2026-11-15**, on a GeoPackage of the
seven runs written by the freeze script.

To regenerate after a deliberate change of output: bump
`gisfire_algorithms.__version__`, create an empty database, migrate it and run

```bash
GISFIRE_DB_NAME=scratch ... alembic upgrade head
python3 test/fixtures/data/alaska_uswfs_regression/freeze_cellsearch_2019-06-30.py \
    --db-url postgresql+psycopg://user@host:port/scratch --gpkg /tmp/check.gpkg
```

then check the runs in QGIS and commit the new JSON.

## Source and licence

**Source:** U.S. Wildland Fire Service (USWFS), Alaska Geographic Area: Alaska
Lightning Detection Network (ALDN). The release's metadata states: "None, these
data are considered public domain". It asks that the USWFS be cited as the
source and that any modification be described.

**Modification:** a selection of the rows, the 25 hours above; no value was
changed. The expected result is derived from them.
