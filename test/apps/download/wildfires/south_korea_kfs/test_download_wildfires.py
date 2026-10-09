#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Korea Forest Service (Safemap IF_0088) download application.

No database and no network: a fake HTTP session returns queued responses and
records what it was asked for. The response envelope and the error responses are
the ones the live service produces — in particular an application error arrives as
HTTP 500 with a JSON body carrying ``header.resultCode``.
"""

import json
import logging
import math

import pytest
import requests

from src.apps.download.wildfires.south_korea_kfs import download_wildfires as app

logger = logging.getLogger("test-kfs-download")

KEY = "TESTKEY1-ABCD-ABCD-ABCD-ABCDEFGH12"


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeResponse:
    """The parts of ``requests.Response`` the client touches."""

    def __init__(self, status_code=200, payload=None, body=""):
        self.status_code = status_code
        self._payload = payload
        self.text = body

    def json(self):
        if self._payload is None:
            raise ValueError("Expecting value")
        return self._payload


class FakeHttpSession:
    """Returns queued responses (or raises queued exceptions) and records calls.

    The last response repeats once the queue runs dry.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def client(responses, retries=2) -> app.SafemapClient:
    """A client wired to a fake session, with the waiting turned off."""
    return app.SafemapClient(service_key=KEY, delay=0.0, retries=retries,
                             session=FakeHttpSession(responses))


def record(objt_id, year="2024", x="1.41332643E7", y="4503340.19"):
    """One record shaped like the service's (Gwanak-gu, Seoul by default)."""
    return {"objt_id": str(objt_id), "occu_year": year, "occu_date": f"{year}0609",
            "occu_tm": "1107", "adres": "서울특별시 관악구 봉천동 산4-2",
            "resn": "담뱃불실화", "ar": "0.0", "amount": "0.0", "x": x, "y": y}


def page(records, total, page_no=1, size=10):
    """A successful response holding ``records``."""
    return FakeResponse(200, {
        "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
        "body": {"items": {"item": records}, "numOfRows": size, "pageNo": page_no,
                 "totalCount": total},
    })


def refused(code, message):
    """An application error, as this service sends it: a 500 with a JSON body."""
    return FakeResponse(500, {"header": {"resultCode": code, "resultMsg": message},
                              "body": {"items": {}}})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Backoff sleeps are real ``time.sleep`` calls; skip them."""
    monkeypatch.setattr(app.time, "sleep", lambda seconds: None)


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

def test_client_sends_key_and_paging():
    c = client([page([], 0)])
    c.get(app.DEFAULT_URL, 3, 250, logger)
    params = c.session.calls[0]["params"]
    assert params == {"serviceKey": KEY, "pageNo": 3, "numOfRows": 250, "returnType": "json"}
    assert c.session.headers["User-Agent"] == app.USER_AGENT


def test_client_unregistered_key_is_not_retried_and_says_what_to_do():
    c = client([refused("30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR")])
    with pytest.raises(app.DownloadError, match="사용신청"):
        c.get(app.DEFAULT_URL, 1, 1, logger)
    assert c.requests_made == 1


def test_client_quota_exhausted_is_not_retried():
    c = client([refused("22", "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR")])
    with pytest.raises(app.DownloadError, match="tomorrow"):
        c.get(app.DEFAULT_URL, 1, 1, logger)
    assert c.requests_made == 1


def test_client_retries_a_transient_result_code():
    c = client([refused("05", "SERVICETIMEOUT_ERROR"), page([record(1)], 1)])
    body = c.get(app.DEFAULT_URL, 1, 1, logger)
    assert body["totalCount"] == 1
    assert c.requests_made == 2


def test_client_retries_a_bare_502_then_gives_up():
    c = client([FakeResponse(502, None, "<html>Bad Gateway</html>")], retries=2)
    with pytest.raises(app.DownloadError, match="after 3 attempt"):
        c.get(app.DEFAULT_URL, 1, 1, logger)
    assert c.requests_made == 3


def test_client_does_not_retry_a_bare_404():
    c = client([FakeResponse(404, None, "Not Found")])
    with pytest.raises(app.DownloadError, match="HTTP 404"):
        c.get(app.DEFAULT_URL, 1, 1, logger)
    assert c.requests_made == 1


def test_client_redacts_the_key_from_connection_errors():
    error = requests.ConnectionError(f"Max retries exceeded with url: /IF_0088?serviceKey={KEY}")
    c = client([error], retries=0)
    with pytest.raises(app.DownloadError) as raised:
        c.get(app.DEFAULT_URL, 1, 1, logger)
    assert KEY not in str(raised.value)
    assert "***" in str(raised.value)


def test_client_no_data_code_is_an_empty_result():
    c = client([FakeResponse(200, {"header": {"resultCode": "03"},
                                   "body": {"items": "", "totalCount": 0}})])
    body = c.get(app.DEFAULT_URL, 1, 1, logger)
    assert app.page_items(body) == []


def test_redact_handles_the_url_encoded_form():
    secret = "a/b+c=="
    assert app.redact("k=a%2Fb%2Bc%3D%3D and a/b+c==", secret) == "k=*** and ***"


# --------------------------------------------------------------------------
# Envelope and paging
# --------------------------------------------------------------------------

@pytest.mark.parametrize("items, expected", [
    ({"item": [{"objt_id": "1"}, {"objt_id": "2"}]}, 2),
    ({"item": {"objt_id": "1"}}, 1),
    ({}, 0),
    ("", 0),
    ([{"objt_id": "1"}], 1),
])
def test_page_items_accepts_every_envelope_shape(items, expected):
    assert len(app.page_items({"items": items})) == expected


def test_fetch_records_pages_until_the_total():
    c = client([page([record(i) for i in range(1, 3)], 5),
                page([record(i) for i in range(3, 5)], 5),
                page([record(5)], 5)])
    records, expected = app.fetch_records(c, app.DEFAULT_URL, 2, logger)
    assert expected == 5
    assert [r["objt_id"] for r in records] == ["1", "2", "3", "4", "5"]
    assert [call["params"]["pageNo"] for call in c.session.calls] == [1, 2, 3]


def test_fetch_records_stops_on_a_clamped_page():
    # Asked for 3 per page, got 2 while 5 remain: pageNo arithmetic would skip.
    c = client([page([record(1), record(2)], 5)])
    with pytest.raises(app.DownloadError, match="smaller --page-size"):
        app.fetch_records(c, app.DEFAULT_URL, 3, logger)


def test_fetch_records_stops_on_an_early_empty_page():
    c = client([page([record(1), record(2)], 5), page([], 5)])
    with pytest.raises(app.DownloadError):
        app.fetch_records(c, app.DEFAULT_URL, 2, logger)


def test_fetch_records_empty_dataset_is_one_request():
    c = client([page([], 0)])
    assert app.fetch_records(c, app.DEFAULT_URL, 500, logger) == ([], 0)
    assert c.requests_made == 1


def test_total_count_asks_for_one_row():
    c = client([page([record(1)], 6551)])
    assert app.total_count(c, app.DEFAULT_URL, logger) == 6551
    assert c.session.calls[0]["params"]["numOfRows"] == 1


# --------------------------------------------------------------------------
# Records to features
# --------------------------------------------------------------------------

def test_web_mercator_round_trip_against_known_points():
    # Origin, and a point whose forward projection is computed here.
    assert app.web_mercator_to_wgs84(0.0, 0.0) == (0.0, 0.0)
    longitude, latitude = 126.9, 37.5
    x = math.radians(longitude) * app.WEB_MERCATOR_RADIUS
    y = math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2)) * app.WEB_MERCATOR_RADIUS
    back = app.web_mercator_to_wgs84(x, y)
    assert back == pytest.approx((longitude, latitude), abs=1e-9)


def test_to_feature_places_the_sample_records_where_their_addresses_are():
    # Sample rows from the dataset page: Gwanak-gu (Seoul) and Changpo-dong (Pohang).
    seoul = app.to_feature(record(1689, x="1.41332643E7", y="4503340.19"))
    pohang = app.to_feature(record(3859, x="1.43994912065E7", y="4310320.30206"))
    assert seoul["geometry"]["coordinates"] == pytest.approx([126.96, 37.46], abs=0.01)
    assert pohang["geometry"]["coordinates"] == pytest.approx([129.35, 36.08], abs=0.01)
    assert seoul["properties"]["x"] == "1.41332643E7"


@pytest.mark.parametrize("x, y", [("", ""), (None, None), ("nan", "1"), ("abc", "1")])
def test_to_feature_without_usable_coordinates_has_null_geometry(x, y):
    assert app.to_feature(record(1, x=x, y=y))["geometry"] is None


def test_outside_bounds_counts_points_off_korea():
    features = [app.to_feature(record(1)), app.to_feature(record(2, x="0", y="0")),
                app.to_feature(record(3, x="", y=""))]
    assert app.outside_bounds(features) == 1


def test_duplicate_ids_and_counts_by_year():
    records = [record(1, "2015"), record(2, "2015"), record(2, "2016"), record(3, "")]
    assert app.duplicate_ids(records) == ["2"]
    assert app.counts_by_year(records) == {"2015": 2, "2016": 1, "undated": 1}


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------

def arguments(tmp_path, *extra):
    return app.parse_arguments(["all", "--output-dir", str(tmp_path), "--delay", "0",
                                "--service-key", KEY, *extra])


def test_download_writes_geojson_and_a_sidecar_without_the_key(tmp_path):
    c = client([page([record(1, "2015"), record(2, "2016")], 3),
                page([record(3, "2016")], 3)])
    written = app.download(c, arguments(tmp_path, "--page-size", "2"), logger)
    assert written == 3

    data_path, meta_path = app.output_paths(tmp_path)
    collection = json.loads(data_path.read_text(encoding="utf-8"))
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 3
    assert collection["features"][0]["properties"]["adres"].startswith("서울특별시")

    meta_text = meta_path.read_text(encoding="utf-8")
    meta = json.loads(meta_text)
    assert meta["records"] == {"expected": 3, "written": 3, "without_geometry": 0,
                               "by_year": {"2015": 1, "2016": 2}}
    assert "KOGL" in meta["source"]["licence"]
    assert KEY not in meta_text
    assert KEY not in data_path.read_text(encoding="utf-8")


def test_download_refuses_to_write_duplicates(tmp_path):
    c = client([page([record(1), record(2)], 3), page([record(2)], 3)])
    with pytest.raises(app.DownloadError, match="more than once"):
        app.download(c, arguments(tmp_path, "--page-size", "2"), logger)
    assert not app.output_paths(tmp_path)[0].exists()


def test_download_skips_an_existing_file_unless_overwritten(tmp_path):
    data_path, _ = app.output_paths(tmp_path)
    data_path.write_text("{}", encoding="utf-8")
    c = client([page([record(1)], 1)])
    assert app.download(c, arguments(tmp_path), logger) == -1
    assert c.requests_made == 0
    assert app.download(c, arguments(tmp_path, "--overwrite"), logger) == 1


def test_main_reports_a_refused_key_without_printing_it(monkeypatch, caplog):
    session = FakeHttpSession([refused("30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR")])
    monkeypatch.setattr(app.requests, "Session", lambda: session)
    with caplog.at_level(logging.INFO):
        status = app.main(["count", "--service-key", KEY, "--delay", "0"])
    assert status == 1
    assert "사용신청" in caplog.text
    assert KEY not in caplog.text


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def test_parse_arguments_reads_the_key_from_the_environment(monkeypatch):
    monkeypatch.setenv(app.SERVICE_KEY_VARIABLE, KEY)
    # The default is read when the parser is built, so it sees the variable.
    assert app.parse_arguments(["count"]).service_key == KEY


def test_parse_arguments_requires_a_key(monkeypatch):
    monkeypatch.delenv(app.SERVICE_KEY_VARIABLE, raising=False)
    with pytest.raises(SystemExit):
        app.parse_arguments(["count"])


@pytest.mark.parametrize("extra", [["--delay", "-1"], ["--page-size", "0"]])
def test_parse_arguments_rejects_bad_politeness(extra):
    with pytest.raises(SystemExit):
        app.parse_arguments(["all", "--service-key", KEY, *extra])
