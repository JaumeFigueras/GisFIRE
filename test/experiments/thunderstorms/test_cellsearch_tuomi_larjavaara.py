#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The statistics and the CSV file of the Cellsearch sensitivity analysis.

The database part (the sweep, the stored thunderstorms, the recount of a
country's flashes) was checked against independent SQL on FMI's regression day;
these tests pin down the arithmetic and the file.
"""

import csv
import datetime
import math

import pytest

from gisfire_algorithms.thunderstorm import CellsearchParameters
from gisfire_experiments.thunderstorms import cellsearch_tuomi_larjavaara as sweep
from gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara import FlashCounts
from gisfire_experiments.thunderstorms.cellsearch_tuomi_larjavaara import Storm

UTC = datetime.timezone.utc


def test_the_statistics_of_a_run():
    storms = [Storm(flashes=10, flashes_in_region=10, area_km2=100.0, duration_min=30.0),
              Storm(flashes=20, flashes_in_region=20, area_km2=400.0, duration_min=60.0),
              Storm(flashes=6, flashes_in_region=6, area_km2=50.0, duration_min=12.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=48, discarded=2))
    assert result["thunderstorms"] == 3
    assert result["flashes_discarded_error"] == 2
    assert result["flashes_clustered"] == 48
    # 36 flashes in thunderstorms: 12 isolated, a quarter.
    assert result["flashes_isolated"] == 12
    assert result["isolated_pct"] == pytest.approx(25.0)
    # Densities 10, 5 and 12 flashes per 100 km²: the median is 10.
    assert result["density_median_per_100km2"] == pytest.approx(10.0)
    assert result["diameter_mean_km"] == pytest.approx(
        (2 * math.sqrt(100 / math.pi) + 2 * math.sqrt(400 / math.pi) + 2 * math.sqrt(50 / math.pi)) / 3)
    assert result["duration_median_min"] == pytest.approx(30.0)


def test_an_even_number_of_thunderstorms_takes_the_mean_of_the_middle_two():
    storms = [Storm(flashes=5, flashes_in_region=5, area_km2=100.0, duration_min=10.0),
              Storm(flashes=10, flashes_in_region=10, area_km2=100.0, duration_min=20.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=15, discarded=0))
    assert result["density_median_per_100km2"] == pytest.approx(7.5)
    assert result["duration_median_min"] == pytest.approx(15.0)


def test_a_thunderstorm_without_area_counts_but_has_no_density_or_diameter():
    storms = [Storm(flashes=5, flashes_in_region=5, area_km2=None, duration_min=10.0),
              Storm(flashes=10, flashes_in_region=10, area_km2=100.0, duration_min=20.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=15, discarded=0))
    assert result["thunderstorms"] == 2
    assert result["density_median_per_100km2"] == pytest.approx(10.0)
    assert result["diameter_mean_km"] == pytest.approx(2 * math.sqrt(100 / math.pi))
    assert result["duration_median_min"] == pytest.approx(15.0)


def test_a_run_without_thunderstorms_has_empty_statistics():
    result = sweep.thunderstorm_statistics([], FlashCounts(clustered=7, discarded=1))
    assert result["thunderstorms"] == 0
    assert result["flashes_isolated"] == 7
    assert result["isolated_pct"] == pytest.approx(100.0)
    assert result["density_median_per_100km2"] is None
    assert result["diameter_mean_km"] is None
    assert result["duration_median_min"] is None


def test_a_run_without_flashes_has_no_isolated_share():
    result = sweep.thunderstorm_statistics([], FlashCounts(clustered=0, discarded=0))
    assert result["isolated_pct"] is None


def test_in_a_region_a_thunderstorm_counts_with_more_than_half_its_flashes_there():
    storms = [Storm(flashes=10, flashes_in_region=6, area_km2=100.0, duration_min=10.0),
              Storm(flashes=10, flashes_in_region=5, area_km2=100.0, duration_min=20.0),
              Storm(flashes=10, flashes_in_region=0, area_km2=100.0, duration_min=30.0)]
    result = sweep.thunderstorm_statistics(storms, FlashCounts(clustered=20, discarded=0))
    assert result["thunderstorms"] == 1
    assert result["duration_median_min"] == pytest.approx(10.0)
    # The region's flashes in any thunderstorm are not isolated: 20 - (6 + 5).
    assert result["flashes_isolated"] == 9


def test_the_file_name_holds_the_algorithm_provider_country_and_period():
    start = datetime.datetime(2022, 8, 19, tzinfo=UTC)
    end = datetime.datetime(2022, 8, 20, 2, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
    assert sweep.csv_filename("FMI", start, end) == \
        "cellsearch_tuomi_larjavaara_FMI_20220819T000000Z_20220820T000000Z.csv"
    assert sweep.csv_filename("FMI", start, end, "Finland") == \
        "cellsearch_tuomi_larjavaara_FMI_Finland_20220819T000000Z_20220820T000000Z.csv"
    assert sweep.csv_filename("USWFS", start, end, "United States") == \
        "cellsearch_tuomi_larjavaara_USWFS_United_States_20220819T000000Z_20220820T000000Z.csv"


def test_the_file_has_one_row_per_experiment_with_its_parameters_and_statistics(tmp_path):
    off = CellsearchParameters(srid=3067)
    limited = CellsearchParameters(attraction_radius_km=10, time_distance_limit_min_km=40,
                                   srid=3067)
    results = {
        off: sweep.thunderstorm_statistics(
            [Storm(flashes=10, flashes_in_region=10, area_km2=100.0, duration_min=30.0)],
            FlashCounts(clustered=40, discarded=3)),
        limited: sweep.thunderstorm_statistics([], FlashCounts(clustered=40, discarded=3)),
    }
    path = tmp_path / "out" / "sweep.csv"
    sweep.write_csv(path, {off: 7, limited: 8}, results)
    rows = list(csv.reader(path.open()))
    assert rows[0] == sweep.CSV_COLUMNS
    assert rows[1] == ["7", "15", "15", "20", "", "1", "3", "40", "30", "75.0000", "10.0000",
                       f"{2 * math.sqrt(100 / math.pi):.4f}", "30.0000"]
    assert rows[2] == ["8", "10", "15", "20", "40", "0", "3", "40", "40", "100.0000", "", "", ""]
