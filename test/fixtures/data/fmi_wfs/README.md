# FMI WFS responses

Real responses of the Finnish Meteorological Institute's open-data WFS
(`https://opendata.fmi.fi/wfs`, stored query
`fmi::observations::lightning::multipointcoverage`, all sixteen parameters),
saved on 2026-11-14 for the tests of
`src/apps/download/lightnings/finland_fmi/download_lightnings.py`.

| File | Request | HTTP |
|------|---------|------|
| `strokes_2023-07-01T1200_1201.xml` | 2023-07-01 12:00 to 12:01 UTC: 17 strokes | 200 |
| `empty_1997-07-01T1200_1300.xml` | 1997-07-01 12:00 to 13:00 UTC: before the archive | 200 |
| `exception_too_long.xml` | 168 hours and one second | 400 |
| `exception_unknown_parameter.xml` | the sixteen parameters plus `foo` | 400 |

Source: Finnish Meteorological Institute (FMI), open data, CC BY 4.0
(https://en.ilmatieteenlaitos.fi/open-data-licence). Unmodified.
