# US Census Bureau Cartographic Boundary Files sample

`cb_2025_us_state_500k.zip` and `cb_2025_us_county_500k.zip` hold four states and
their counties cut from the Census Bureau's 2025 Cartographic Boundary Files at
1:500,000, `cb_2025_us_state_500k.zip` and `cb_2025_us_county_500k.zip`, downloaded
on 2026-11-21 from <https://www2.census.gov/geo/tiger/GENZ2025/shp/>.

**Source:** U.S. Census Bureau, 2025 Cartographic Boundary Files. A work of the US
federal government, in the public domain. **Modification:** only a selection of the
features (`STATEFP IN ('10', '11', '44', '66')`), written again with `ogr2ogr` under
the published names; no value or vertex was changed, and the ISO metadata files of
the release are not included.

The features were chosen for what the import has to get right:

- Delaware (10) and its 3 counties, and Rhode Island (44) and its 5: both have a
  **Kent County** (10001 and 44003), so a county must find its parent by code, not
  by name;
- the District of Columbia (11), a state equivalent whose one county equivalent
  (11001) has LSAD `00`;
- Guam (66) and its one county equivalent (66010), a territory that must be left
  out.

12 boundaries are imported: 3 states and 9 counties.
