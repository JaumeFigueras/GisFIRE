#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the INAB (Guatemala) fire download application.

There is no database here and no network: a fake HTTP session returns queued
responses and records what it was asked for, which is how the paging, the
retrying and the politeness are exercised without touching INAB's server. What a
download application has to get right is almost entirely *what it sends* and
*when it stops*, and both are observable from the call log.

The response shapes are the ones this server really produces, including the two
that caused trouble: ``exceededTransferLimit`` appearing in different places for a
feature layer and a table, and a large query coming back as a body that is cut off
mid-JSON rather than as an error.
"""

import datetime
import json
import logging

from pathlib import Path

import pytest
import requests

from src.apps.download.wildfires.guatemala_inab import download_wildfires as app

logger = logging.getLogger("test-inab-download")


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeResponse:
    """The parts of ``requests.Response`` the client actually touches."""

    def __init__(self, status_code=200, payload=None, body=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = body if body is not None else ""
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("Expecting ',' delimiter: line 1 column 32936356")
        return self._payload


class FakeHttpSession:
    """Returns queued responses and records the parameters it was called with.

    ``responses`` may hold :class:`FakeResponse` objects or exceptions; an
    exception is raised instead of returned, which is how a connection failure is
    simulated. The last response repeats once the queue runs dry, so a test that
    only cares about the happy path need queue one.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params or {}, "timeout": timeout})
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def client(responses, delay=0.0, retries=2) -> app.ArcGisClient:
    """A client wired to a fake session, with the waiting turned off."""
    return app.ArcGisClient(delay=delay, retries=retries,
                            session=FakeHttpSession(responses))


def features(count, start=1, geometry=True):
    """``count`` GeoJSON features shaped like the server's."""
    return [
        {"type": "Feature",
         "id": oid,
         "geometry": {"type": "Point", "coordinates": [-90.5, 15.0]} if geometry else None,
         "properties": {"objectid": oid,
                        "fecha_hora_incendio": 1674076500000,
                        "municipio": f"m{oid}"}}
        for oid in range(start, start + count)
    ]


def count_response(n):
    return FakeResponse(payload={"count": n})


def page_response(count, start=1, geometry=True):
    return FakeResponse(payload={"type": "FeatureCollection",
                                 "features": features(count, start, geometry)})


LAYER_METADATA = {
    "name": "datos_generales",
    "type": "Feature Layer",
    "geometryType": "esriGeometryPoint",
    "objectIdField": "objectid",
    "maxRecordCount": 50000,
    "fields": [
        {"name": "objectid", "type": "esriFieldTypeOID"},
        {"name": "fecha_hora_incendio", "type": "esriFieldTypeDate"},
        {"name": "created_date", "type": "esriFieldTypeDate"},
        {"name": "municipio", "type": "esriFieldTypeString"},
    ],
}

REPORTS = app.DATASETS["fire-reports"]
SCARS = app.DATASETS["burn-scars"]
NO_YEAR = app.DATASETS["burn-scars-2024"]


def arguments(**overrides):
    """A parsed namespace for the download helpers, without going through argparse."""
    values = {"root": app.DEFAULT_ROOT, "output_dir": Path("."), "overwrite": False,
              "iso_dates": False, "page_size": 500}
    values.update(overrides)
    import argparse
    return argparse.Namespace(**values)


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------

def test_the_default_dataset_is_the_fire_reports():
    """The layer behind the viewer, and the only one with a per-fire date."""
    assert app.DEFAULT_DATASET == "fire-reports"
    assert REPORTS.year_field == "fecha_hora_incendio"
    assert REPORTS.year_is_date is True


def test_every_dataset_has_a_page_size_within_the_layers_own_limit():
    for dataset in app.DATASETS.values():
        assert 1 <= dataset.default_page_size <= dataset.max_record_count, dataset.key


def test_the_polygon_layers_page_far_smaller_than_the_point_ones():
    """The ceiling is on response *bytes*, and a burn scar is ~110 kB on its own.

    500 of them is a ~50 MB body, which this server truncates mid-JSON rather
    than refusing. See the module docstring of the application.
    """
    assert SCARS.default_page_size == 50
    assert app.DATASETS["burn-scars-2024"].default_page_size == 50
    assert REPORTS.default_page_size == 500


def test_the_layer_urls_are_built_from_the_registry():
    assert REPORTS.query_url().endswith(
        "/Hosted/Monitoreo_de_Incendios_Forestales_resultados/FeatureServer/0/query")
    assert SCARS.layer == 2, "the burn scars are layer 2 of their service, not 0"
    assert app.DATASETS["burn-scars-table"].layer == 12


def test_the_table_is_marked_as_having_no_geometry():
    assert app.DATASETS["burn-scars-table"].has_geometry is False
    assert all(d.has_geometry for d in app.DATASETS.values()
               if d.key != "burn-scars-table")


# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------

def test_a_mode_is_required(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments([])
    assert "a mode is required" in capsys.readouterr().err


def test_the_year_mode_needs_a_year(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["year"])
    assert "needs --year" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["years", "all"])
def test_a_year_is_refused_where_it_means_nothing(mode, capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments([mode, "--year", "2025"])
    assert "only applies to the 'year' mode" in capsys.readouterr().err


def test_the_page_size_defaults_to_the_datasets_own():
    assert app.parse_arguments(["all"]).page_size == 500
    assert app.parse_arguments(["all", "-d", "burn-scars"]).page_size == 50


def test_the_page_size_may_be_overridden():
    assert app.parse_arguments(["all", "--page-size", "10"]).page_size == 10


def test_a_page_size_above_the_layers_limit_is_refused(capsys):
    """The server would clamp it, and the run's paging arithmetic would then be wrong."""
    with pytest.raises(SystemExit):
        app.parse_arguments(["all", "-d", "burn-scars", "--page-size", "5000"])
    assert "maxRecordCount" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_a_page_size_below_one_is_refused(bad, capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["all", "--page-size", bad])
    assert "at least 1" in capsys.readouterr().err


def test_a_negative_delay_is_refused(capsys):
    with pytest.raises(SystemExit):
        app.parse_arguments(["all", "--delay", "-1"])
    assert "cannot be negative" in capsys.readouterr().err


def test_the_delay_defaults_to_a_polite_one_second():
    assert app.parse_arguments(["all"]).delay == app.DEFAULT_DELAY == 1.0


def test_listing_the_datasets_needs_no_mode():
    """--list-datasets is the one thing that runs on its own."""
    parsed = app.parse_arguments(["--list-datasets"])
    assert parsed.list_datasets is True
    assert parsed.mode is None


def test_dates_are_left_as_published_unless_asked():
    assert app.parse_arguments(["all"]).iso_dates is False


# --------------------------------------------------------------------------
# The where clause
# --------------------------------------------------------------------------

def test_a_date_field_is_filtered_with_extract():
    assert app.year_filter(REPORTS, 2023) == \
        "EXTRACT(YEAR FROM fecha_hora_incendio) = 2023"


def test_an_integer_year_field_is_compared_directly():
    assert app.year_filter(SCARS, 2025) == "fecha_ano = 2025"


def test_everything_is_selected_with_1_equals_1():
    """An empty where is rejected by some ArcGIS versions; 1=1 never is."""
    assert app.year_filter(REPORTS, None) == "1=1"
    assert app.year_filter(NO_YEAR, None) == "1=1"


def test_a_year_cannot_be_asked_of_a_layer_that_publishes_none():
    with pytest.raises(ValueError, match="publishes no year field"):
        app.year_filter(NO_YEAR, 2024)


# --------------------------------------------------------------------------
# Counting
# --------------------------------------------------------------------------

def test_the_count_is_asked_for_before_anything_is_downloaded():
    fake = client([count_response(187)])
    assert app.feature_count(fake, REPORTS, "1=1", logger) == 187

    sent = fake.session.calls[0]["params"]
    assert sent["returnCountOnly"] == "true"
    assert sent["f"] == "json"


def test_a_response_with_no_count_is_an_error():
    with pytest.raises(app.DownloadError, match="did not return a count"):
        app.feature_count(client([FakeResponse(payload={"features": []})]),
                          REPORTS, "1=1", logger)


def test_the_years_are_counted_in_one_grouped_request():
    """A count query per year would have to be told which years to try."""
    fake = client([FakeResponse(payload={"features": [
        {"attributes": {"EXPR_1": 2024, "n": 727}},
        {"attributes": {"EXPR_1": 2023, "n": 187}},
        {"attributes": {"EXPR_1": 2026, "n": 1908}},
        {"attributes": {"EXPR_1": 2025, "n": 1789}},
    ]})])
    counts = app.counts_by_year(fake, REPORTS, logger)

    assert len(fake.session.calls) == 1
    assert counts == {"2023": 187, "2024": 727, "2025": 1789, "2026": 1908}
    assert list(counts) == sorted(counts), "oldest first"


def test_records_with_no_date_are_reported_rather_than_dropped():
    """Four fire reports have no date. They exist and the 'year' mode cannot reach them."""
    fake = client([FakeResponse(payload={"features": [
        {"attributes": {"EXPR_1": 2023, "n": 187}},
        {"attributes": {"EXPR_1": None, "n": 4}},
    ]})])
    counts = app.counts_by_year(fake, REPORTS, logger)

    assert counts == {"2023": 187, app.UNDATED_LABEL: 4}
    assert list(counts)[-1] == app.UNDATED_LABEL, "the undated bucket goes last"


def test_an_integer_year_field_groups_under_its_own_name():
    """The grouped column is 'EXPR_1' for an expression but 'fecha_ano' for a field."""
    fake = client([FakeResponse(payload={"features": [
        {"attributes": {"fecha_ano": 2025, "n": 1337}},
    ]})])
    assert app.counts_by_year(fake, SCARS, logger) == {"2025": 1337}


def test_counting_years_on_a_layer_with_none_is_refused():
    with pytest.raises(ValueError, match="no year field"):
        app.counts_by_year(client([count_response(0)]), NO_YEAR, logger)


def test_the_undated_bucket_is_not_a_downloadable_year():
    assert app.downloadable_years({"2023": 1, "2025": 2, app.UNDATED_LABEL: 4}) == \
        [2023, 2025]


# --------------------------------------------------------------------------
# Paging
# --------------------------------------------------------------------------

def test_a_page_is_ordered_and_asks_for_everything():
    """Paging an unordered result is undefined: two pages can overlap or skip."""
    fake = client([page_response(2)])
    app.fetch_page(fake, REPORTS, "1=1", 0, 2, logger)

    sent = fake.session.calls[0]["params"]
    assert sent["orderByFields"] == "objectid ASC"
    assert sent["outFields"] == "*"
    assert sent["outSR"] == app.OUTPUT_SRID == 4326
    assert sent["f"] == "geojson"
    assert sent["resultOffset"] == 0
    assert sent["resultRecordCount"] == 2


def test_a_table_is_queried_without_geometry():
    fake = client([page_response(1, geometry=False)])
    app.fetch_page(fake, app.DATASETS["burn-scars-table"], "1=1", 0, 10, logger)
    assert fake.session.calls[0]["params"]["returnGeometry"] == "false"


def test_paging_follows_the_offsets_and_stops_on_a_short_page():
    fake = client([page_response(100, start=1),
                   page_response(100, start=101),
                   page_response(87, start=201)])
    got = app.fetch_features(fake, REPORTS, "1=1", 100, logger, expected=287)

    assert len(got) == 287
    assert [call["params"]["resultOffset"] for call in fake.session.calls] == [0, 100, 200]


def test_paging_stops_without_a_wasted_request_when_the_first_page_is_short():
    fake = client([page_response(87)])
    assert len(app.fetch_features(fake, REPORTS, "1=1", 100, logger, expected=87)) == 87
    assert len(fake.session.calls) == 1


def test_a_full_last_page_costs_one_more_request_and_stops_on_the_count():
    """A server that ignored resultOffset would otherwise page for ever."""
    fake = client([page_response(100, start=1), page_response(100, start=1)])
    got = app.fetch_features(fake, REPORTS, "1=1", 100, logger, expected=100)

    assert len(got) == 100
    assert len(fake.session.calls) == 1


def test_paging_does_not_trust_exceeded_transfer_limit():
    """Its position moves between response shapes; a short page is the reliable signal.

    Here the flag says there is more and there is not — a feature layer that
    omits it entirely would be the mirror image, and both have to work.
    """
    fake = client([FakeResponse(payload={
        "type": "FeatureCollection",
        "features": features(50),
        "properties": {"exceededTransferLimit": True},
    })])
    assert len(app.fetch_features(fake, REPORTS, "1=1", 100, logger, expected=50)) == 50
    assert len(fake.session.calls) == 1


# --------------------------------------------------------------------------
# Politeness
# --------------------------------------------------------------------------

def test_the_client_identifies_itself():
    """A downloader that does not say what it is looks exactly like a scraper."""
    fake = client([count_response(1)])
    assert "GisFIRE" in fake.session.headers["User-Agent"]


def test_the_delay_is_enforced_between_requests(monkeypatch):
    slept = []
    monkeypatch.setattr(app.time, "sleep", slept.append)
    # A monotonic clock that never advances, so every gap looks like zero and the
    # full delay is owed before each request after the first.
    monkeypatch.setattr(app.time, "monotonic", lambda: 1000.0)

    fake = client([page_response(1)], delay=2.5)
    for _ in range(3):
        fake.get("http://example.invalid", {}, logger)

    assert slept == [2.5, 2.5], "waited before every request but the first"


def test_the_request_count_is_tracked_for_the_log():
    fake = client([page_response(1)])
    for _ in range(4):
        fake.get("http://example.invalid", {}, logger)
    assert fake.requests_made == 4


# --------------------------------------------------------------------------
# Failure handling
# --------------------------------------------------------------------------

def test_a_retryable_status_is_retried(monkeypatch):
    monkeypatch.setattr(app.time, "sleep", lambda _: None)
    fake = client([FakeResponse(status_code=503), count_response(7)], retries=3)

    assert app.feature_count(fake, REPORTS, "1=1", logger) == 7
    assert fake.requests_made == 2


def test_a_refusal_is_not_retried(monkeypatch):
    """A 400 would fail identically however often it is sent."""
    monkeypatch.setattr(app.time, "sleep", lambda _: None)
    fake = client([FakeResponse(status_code=400)], retries=3)

    with pytest.raises(app.DownloadError, match="after 1 attempt"):
        app.feature_count(fake, REPORTS, "1=1", logger)
    assert fake.requests_made == 1


def test_a_connection_error_is_retried(monkeypatch):
    monkeypatch.setattr(app.time, "sleep", lambda _: None)
    fake = client([requests.ConnectionError("no route"), count_response(3)], retries=2)
    assert app.feature_count(fake, REPORTS, "1=1", logger) == 3


def test_the_retry_budget_runs_out(monkeypatch):
    monkeypatch.setattr(app.time, "sleep", lambda _: None)
    fake = client([FakeResponse(status_code=503)], retries=2)

    with pytest.raises(app.DownloadError, match="after 3 attempt"):
        app.feature_count(fake, REPORTS, "1=1", logger)


def test_retry_after_is_honoured_but_capped(monkeypatch):
    slept = []
    monkeypatch.setattr(app.time, "sleep", slept.append)
    fake = client([FakeResponse(status_code=429, headers={"Retry-After": "9999"}),
                   count_response(1)], retries=2)

    app.feature_count(fake, REPORTS, "1=1", logger)
    assert slept == [app.MAX_RETRY_AFTER], "a server asking for an hour is capped"


def test_an_unparseable_retry_after_falls_back_to_the_backoff(monkeypatch):
    """The header may be an HTTP date; the normal backoff is a fine answer."""
    slept = []
    monkeypatch.setattr(app.time, "sleep", slept.append)
    fake = client([FakeResponse(status_code=503,
                                headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
                   count_response(1)], retries=2)

    app.feature_count(fake, REPORTS, "1=1", logger)
    assert slept == [app.BACKOFF_BASE]


def test_an_arcgis_error_document_is_not_mistaken_for_an_empty_result():
    """ArcGIS reports a rejected query as HTTP 200 with an error object in the body."""
    fake = client([FakeResponse(payload={"error": {
        "code": 400, "message": "Unable to complete operation.",
        "details": ["Invalid field: fecha_hora_incendio"]}})])

    with pytest.raises(app.DownloadError, match="Invalid field"):
        app.feature_count(fake, REPORTS, "1=1", logger)


def test_a_truncated_body_says_to_use_a_smaller_page(monkeypatch):
    """This server cuts a large response off mid-JSON rather than refusing it.

    Asking for 500 burn-scar polygons really does produce a ~50 MB body that ends
    in the middle of a coordinate. The message has to name the fix, because
    "expecting ',' delimiter" names nothing.
    """
    monkeypatch.setattr(app.time, "sleep", lambda _: None)
    body = '{"features":[{"geometry":{"type":"MultiPolygon","coordinates":[[[[-90.58'
    fake = client([FakeResponse(payload=None, body=body)], retries=3)

    with pytest.raises(app.DownloadError, match="smaller --page-size"):
        app.feature_count(fake, REPORTS, "1=1", logger)
    assert fake.requests_made == 1, "not retried: it would be cut off in the same place"


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

def test_the_date_fields_are_read_from_the_server():
    """Not listed here, so a field INAB adds is handled without an edit."""
    fake = client([FakeResponse(payload=LAYER_METADATA)])
    fields, metadata = app.date_fields(fake, REPORTS, logger)

    assert fields == ["fecha_hora_incendio", "created_date"]
    assert metadata["objectIdField"] == "objectid"


def test_epoch_milliseconds_become_iso_utc():
    rows = features(1)
    assert app.to_iso(rows, ["fecha_hora_incendio"]) == 1
    assert rows[0]["properties"]["fecha_hora_incendio"] == "2023-01-18T21:15:00+00:00"


def test_a_value_that_is_not_a_number_is_left_alone():
    """A field already converted must not be mangled by a second pass."""
    rows = [{"properties": {"fecha_hora_incendio": "2023-01-18T21:15:00+00:00"}},
            {"properties": {"fecha_hora_incendio": None}},
            {"properties": {}}]
    assert app.to_iso(rows, ["fecha_hora_incendio"]) == 0
    assert rows[0]["properties"]["fecha_hora_incendio"] == "2023-01-18T21:15:00+00:00"
    assert rows[1]["properties"]["fecha_hora_incendio"] is None


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def test_the_file_names_carry_the_dataset_and_the_year(tmp_path):
    data, meta = app.output_paths(tmp_path, REPORTS, 2025)
    assert data.name == "guatemala_inab_fire-reports_2025.geojson"
    assert meta.name == "guatemala_inab_fire-reports_2025.meta.json"

    data, _ = app.output_paths(tmp_path, SCARS, None)
    assert data.name == "guatemala_inab_burn-scars_all.geojson"


def test_a_download_writes_geojson_and_a_provenance_sidecar(tmp_path):
    fake = client([count_response(2),
                   FakeResponse(payload=LAYER_METADATA),
                   page_response(2)])
    written = app.download(fake, REPORTS, 2023,
                           arguments(output_dir=tmp_path, page_size=100), logger)

    assert written == 2
    data, meta = app.output_paths(tmp_path, REPORTS, 2023)

    collection = json.loads(data.read_text(encoding="utf-8"))
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 2

    sidecar = json.loads(meta.read_text(encoding="utf-8"))
    assert sidecar["records"] == {"expected": 2, "written": 2}
    assert sidecar["query"]["where"] == "EXTRACT(YEAR FROM fecha_hora_incendio) = 2023"
    assert sidecar["source"]["service"] == REPORTS.service
    assert sidecar["dates"]["format"] == "epoch milliseconds UTC"
    assert sidecar["layer_metadata"]["fields"], "the server's own field list is recorded"
    assert any("licence" in note or "stable identifier" in note
               for note in sidecar["caveats"])
    datetime.datetime.fromisoformat(sidecar["downloaded_at"])


def test_the_sidecar_records_that_dates_were_converted(tmp_path):
    fake = client([count_response(1),
                   FakeResponse(payload=LAYER_METADATA),
                   page_response(1)])
    app.download(fake, REPORTS, 2023,
                 arguments(output_dir=tmp_path, page_size=100, iso_dates=True), logger)

    data, meta = app.output_paths(tmp_path, REPORTS, 2023)
    sidecar = json.loads(meta.read_text(encoding="utf-8"))
    assert sidecar["dates"]["format"] == "ISO 8601 UTC"
    assert sidecar["dates"]["converted"] is True

    collection = json.loads(data.read_text(encoding="utf-8"))
    assert collection["features"][0]["properties"]["fecha_hora_incendio"] == \
        "2023-01-18T21:15:00+00:00"


def test_an_existing_file_is_skipped_so_a_run_resumes(tmp_path):
    data, _ = app.output_paths(tmp_path, REPORTS, 2023)
    data.write_text("{}", encoding="utf-8")
    fake = client([count_response(999)])

    assert app.download(fake, REPORTS, 2023,
                        arguments(output_dir=tmp_path), logger) == -1
    assert fake.session.calls == [], "nothing was asked of the server"
    assert data.read_text(encoding="utf-8") == "{}"


def test_overwrite_fetches_it_again(tmp_path):
    data, _ = app.output_paths(tmp_path, REPORTS, 2023)
    data.write_text("{}", encoding="utf-8")
    fake = client([count_response(1),
                   FakeResponse(payload=LAYER_METADATA),
                   page_response(1)])

    assert app.download(fake, REPORTS, 2023,
                        arguments(output_dir=tmp_path, page_size=100,
                                  overwrite=True), logger) == 1
    assert json.loads(data.read_text(encoding="utf-8"))["features"]


def test_a_short_download_is_refused_rather_than_written(tmp_path):
    """A short page is also what a truncated response looks like.

    The count was fetched first precisely so this can be caught; writing a
    quietly incomplete file would be the worst outcome available.
    """
    fake = client([count_response(500),
                   FakeResponse(payload=LAYER_METADATA),
                   page_response(30)])

    with pytest.raises(app.DownloadError, match="said 500 record"):
        app.download(fake, REPORTS, 2023,
                     arguments(output_dir=tmp_path, page_size=100), logger)

    data, _ = app.output_paths(tmp_path, REPORTS, 2023)
    assert not data.exists(), "nothing is written when the count disagrees"


def test_an_empty_year_writes_nothing_and_says_so(tmp_path, caplog):
    fake = client([count_response(0)])
    with caplog.at_level(logging.WARNING):
        assert app.download(fake, REPORTS, 1999,
                            arguments(output_dir=tmp_path), logger) == 0

    assert "0 records" in caplog.text
    data, _ = app.output_paths(tmp_path, REPORTS, 1999)
    assert not data.exists()


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------

def test_the_years_mode_downloads_nothing(tmp_path, capsys):
    fake = client([FakeResponse(payload={"features": [
        {"attributes": {"EXPR_1": 2023, "n": 187}},
        {"attributes": {"EXPR_1": 2024, "n": 727}},
    ]})])
    status = app.run(arguments(mode="years", dataset="fire-reports",
                               output_dir=tmp_path), fake, logger)

    assert status == 0
    assert len(fake.session.calls) == 1
    printed = capsys.readouterr().out
    assert "187" in printed and "727" in printed and "914" in printed
    assert not list(tmp_path.iterdir())


def test_the_years_mode_refuses_a_layer_with_no_year(tmp_path, caplog):
    fake = client([count_response(1405)])
    with caplog.at_level(logging.ERROR):
        status = app.run(arguments(mode="years", dataset="burn-scars-2024",
                                   output_dir=tmp_path), fake, logger)

    assert status == 1
    assert "no year field" in caplog.text
    assert fake.session.calls == []


def test_the_all_mode_asks_for_every_record(tmp_path):
    fake = client([count_response(2),
                   FakeResponse(payload=LAYER_METADATA),
                   page_response(2)])
    status = app.run(arguments(mode="all", dataset="fire-reports",
                               output_dir=tmp_path, page_size=100), fake, logger)

    assert status == 0
    assert fake.session.calls[0]["params"]["where"] == "1=1"
    data, _ = app.output_paths(tmp_path, REPORTS, None)
    assert data.exists()


def test_the_all_mode_works_on_the_layer_with_no_year(tmp_path):
    """It is the only way to get that one, which is what the years mode says."""
    fake = client([count_response(1),
                   FakeResponse(payload=LAYER_METADATA),
                   page_response(1)])
    assert app.run(arguments(mode="all", dataset="burn-scars-2024",
                             output_dir=tmp_path, page_size=50), fake, logger) == 0


# --------------------------------------------------------------------------
# The CLI
# --------------------------------------------------------------------------

def test_listing_the_datasets_prints_them_and_exits(capsys):
    assert app.main(["--list-datasets"]) == 0
    printed = capsys.readouterr().out
    for key in app.DATASETS:
        assert key in printed


def test_a_failure_is_reported_not_raised(monkeypatch, tmp_path):
    def explode(*_args, **_kwargs):
        raise app.DownloadError("the server said no")
    monkeypatch.setattr(app, "run", explode)

    assert app.main(["all", "-o", str(tmp_path)]) == 1
