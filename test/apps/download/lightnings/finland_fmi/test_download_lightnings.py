#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the FMI lightning download application.

No database and no network: a fake HTTP session answers with real responses of
the service, saved in ``test/fixtures/data/fmi_wfs`` — a minute with 17 strokes,
an empty hour, and the two ``ExceptionReport`` answers to a bad request. Source:
Finnish Meteorological Institute (FMI), open data, CC BY 4.0.
"""

import datetime
import gzip
import json
import logging

import pytest
import requests

from src.apps.download.lightnings.finland_fmi import download_lightnings as app
from src.providers import finland_fmi
from src.settings import ROOT_DIR

logger = logging.getLogger("test-fmi-download")

UTC = datetime.timezone.utc
FIXTURES = ROOT_DIR / "test" / "fixtures" / "data" / "fmi_wfs"
STROKES = (FIXTURES / "strokes_2023-07-01T1200_1201.xml").read_bytes()
EMPTY = (FIXTURES / "empty_1997-07-01T1200_1300.xml").read_bytes()
TOO_LONG = (FIXTURES / "exception_too_long.xml").read_bytes()
UNKNOWN_PARAMETER = (FIXTURES / "exception_unknown_parameter.xml").read_bytes()

#: The minute the strokes fixture covers.
MINUTE = (datetime.datetime(2023, 7, 1, 12, 0, tzinfo=UTC),
          datetime.datetime(2023, 7, 1, 12, 1, tzinfo=UTC))

#: The first row of the strokes fixture, as written to the monthly file.
FIRST_ROW = "1688212800,61.09450,29.18070,30645782,1,8,1,3,3,61.6,2.5,0.4,1.7,5.1,1.4,1,0,1,17"


def hours(window):
    start, end = window
    return (end - start) / datetime.timedelta(hours=1)


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeResponse:
    """The parts of ``requests.Response`` the client touches."""

    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


class FakeHttpSession:
    """Answers with ``responder(params)``, or from a queue whose last item repeats.

    An answer that is an exception is raised. Every call is recorded.
    """

    def __init__(self, responder):
        self.responder = responder if callable(responder) else None
        self.responses = None if callable(responder) else list(responder)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        if self.responder is not None:
            response = self.responder(dict(params or {}))
        else:
            response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def strokes_in_july_2023(params):
    """The strokes fixture for the window holding 2023-07-01 12:00, empty elsewhere."""
    if params["starttime"] <= "2023-07-01T12:00:00Z" < params["endtime"]:
        return FakeResponse(200, STROKES)
    return FakeResponse(200, EMPTY)


def client(responder, retries=2) -> app.FmiClient:
    """A client wired to a fake session, with the waiting turned off."""
    return app.FmiClient(delay=0.0, retries=retries, session=FakeHttpSession(responder))


def arguments(output_dir, from_year, to_year=None, overwrite=False, include_current=False):
    now = datetime.datetime(2026, 11, 14, tzinfo=UTC)
    argv = ["--from-year", str(from_year), "--output-dir", str(output_dir)]
    if to_year is not None:
        argv += ["--to-year", str(to_year)]
    if overwrite:
        argv.append("--overwrite")
    if include_current:
        argv.append("--include-current")
    return app.parse_arguments(argv, now)


def read_month(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return handle.read().splitlines()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Backoff sleeps are real ``time.sleep`` calls; skip them."""
    monkeypatch.setattr(app.time, "sleep", lambda seconds: None)


# --------------------------------------------------------------------------
# Months and windows
# --------------------------------------------------------------------------

def test_a_31_day_month_is_five_windows():
    month = app.Month(2023, 7)
    windows = app.month_windows(month.start, month.end)
    assert [hours(window) for window in windows] == [168, 168, 168, 168, 72]
    assert windows[0][0] == month.start and windows[-1][1] == month.end


def test_february_is_exactly_four_windows():
    month = app.Month(2019, 2)
    assert [hours(w) for w in app.month_windows(month.start, month.end)] == [168] * 4


def test_a_leap_february_has_a_short_fifth_window():
    month = app.Month(2020, 2)
    assert [hours(w) for w in app.month_windows(month.start, month.end)] == [168] * 4 + [24]


def test_december_ends_at_the_new_year():
    assert app.Month(2018, 12).end == datetime.datetime(2019, 1, 1, tzinfo=UTC)
    assert app.Month(2018, 12).label == "2018-12"


@pytest.mark.parametrize("number", range(1, 13))
def test_the_windows_tile_the_month_within_the_limit(number):
    """Half-open windows: each starts where the previous ended, none too long."""
    month = app.Month(2020, number)
    windows = app.month_windows(month.start, month.end)
    assert windows[0][0] == month.start and windows[-1][1] == month.end
    assert all(previous[1] == following[0] for previous, following in zip(windows, windows[1:]))
    assert all(0 < hours(window) <= finland_fmi.MAX_REQUEST_HOURS for window in windows)


def test_a_past_year_is_twelve_complete_months():
    now = datetime.datetime(2026, 11, 14, tzinfo=UTC)
    months = app.months_to_download(2018, 2018, now, include_current=False)
    assert [(m.label, complete) for m, complete in months] == \
        [(f"2018-{n:02d}", True) for n in range(1, 13)]


def test_the_year_in_progress_stops_at_the_last_complete_month():
    now = datetime.datetime(2026, 11, 14, 9, 30, tzinfo=UTC)
    months = app.months_to_download(2026, 2026, now, include_current=False)
    assert months[-1] == (app.Month(2026, 10), True)
    assert len(months) == 10


def test_a_month_is_complete_only_a_day_after_it_ends():
    just_after = datetime.datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    assert app.months_to_download(2026, 2026, just_after, False)[-1][0] == app.Month(2026, 9)
    a_day_after = datetime.datetime(2026, 11, 2, tzinfo=UTC)
    assert app.months_to_download(2026, 2026, a_day_after, False)[-1][0] == app.Month(2026, 10)


def test_include_current_adds_the_incomplete_months():
    just_after = datetime.datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    months = app.months_to_download(2026, 2026, just_after, include_current=True)
    assert months[-2:] == [(app.Month(2026, 10), False), (app.Month(2026, 11), False)]


# --------------------------------------------------------------------------
# Parsing a response
# --------------------------------------------------------------------------

def test_a_response_becomes_one_row_per_stroke_as_published():
    window = app.parse_response(STROKES, *MINUTE)
    assert len(window.rows) == 17
    # Latitude first and the trailing zeros kept: the text the service sent.
    assert window.rows[0] == FIRST_ROW
    assert window.timestamp == "2026-11-14T14:50:04Z"
    flash = [row for row in window.rows if row.split(",")[3] == "30645787"]
    assert [row.split(",")[4] for row in flash] == ["4", "0", "0", "0"]
    assert {row.split(",")[0] for row in flash} == {"1688212815"}


def test_every_row_has_the_columns_of_the_file():
    for row in app.parse_response(STROKES, *MINUTE).rows:
        assert len(row.split(",")) == len(app.COLUMNS) == 19


def test_an_empty_window_is_no_rows():
    start = datetime.datetime(1997, 7, 1, 12, tzinfo=UTC)
    window = app.parse_response(EMPTY, start, start + datetime.timedelta(hours=1))
    assert window.rows == []
    assert window.timestamp == "2026-11-14T14:50:05Z"


@pytest.mark.parametrize(("content", "message"), [
    (TOO_LONG, "Too long time interval requested! No more than 168.000000 hours allowed."),
    (UNKNOWN_PARAMETER, "Unknown observation parameter"),
])
def test_an_exception_report_is_an_error_with_its_text(content, message):
    with pytest.raises(app.DownloadError, match="refused") as caught:
        app.parse_response(content, *MINUTE)
    assert message in str(caught.value)
    assert "URI:" not in str(caught.value)


@pytest.mark.parametrize(("altered", "message"), [
    pytest.param(STROKES.replace(b'name="rise_time"', b'name="xx"')
                 .replace(b'name="ptz_time"', b'name="rise_time"')
                 .replace(b'name="xx"', b'name="ptz_time"'), "fields", id="fields-reordered"),
    pytest.param(STROKES.replace(b'<swe:field name="stroke_status"', b'<swe:skip name="stroke_status"'),
                 "fields", id="field-missing"),
    pytest.param(STROKES.replace(b"crs=4258", b"crs=4326"), "ETRS89", id="other-crs"),
    pytest.param(STROKES.replace(b"time=unixtime", b"time=iso"), "Unix time", id="other-time"),
    pytest.param(STROKES.replace(b"30645795 1 13 0 8 13 92.5 0.3 0.1 0.7 6.8 17 1 0 1 17\n", b""),
                 "17 position", id="a-tuple-missing"),
    pytest.param(STROKES.replace(b"30645795 1 13 0 8 13 92.5 0.3 0.1 0.7 6.8 17 1 0 1 17",
                                 b"30645795 1 13 0 8 13 92.5 0.3 0.1 0.7 6.8 17 1 0 1"),
                 "15 value", id="a-value-missing"),
    pytest.param(STROKES.replace(b"61.18740 28.60320 1688212855", b"61.18740 28.60320"),
                 "2 coordinate", id="a-coordinate-missing"),
    pytest.param(STROKES.replace(b"61.18740 28.60320 1688212855", b"61.18740 28.60320 soon"),
                 "time", id="time-not-a-number"),
    pytest.param(STROKES.replace(b"61.18740 28.60320 1688212855", b"61.18740 28.60320 1688212860"),
                 "outside", id="time-at-the-excluded-end"),
    pytest.param(STROKES.replace(b"30645795 1 13", b"30645795 1 1,3"), "comma", id="comma"),
    pytest.param(STROKES.replace(b"</wfs:member>", b"</wfs:member>\n<wfs:member/>"),
                 "2 coverages", id="two-coverages"),
    pytest.param(STROKES.replace(b"gmlcov:MultiPointCoverage", b"gmlcov:Other"),
                 "no MultiPointCoverage", id="no-coverage"),
    pytest.param(b"<html><body>Service unavailable</body></html>", "not a WFS",
                 id="html"),
    pytest.param(b"Service unavailable", "not XML", id="not-xml"),
])
def test_a_response_that_does_not_add_up_is_refused(altered, message):
    with pytest.raises(app.DownloadError, match=message):
        app.parse_response(altered, *MINUTE)


def test_a_stroke_before_the_window_is_refused():
    late_start = MINUTE[0] + datetime.timedelta(seconds=1)
    with pytest.raises(app.DownloadError, match="outside"):
        app.parse_response(STROKES, late_start, MINUTE[1])


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

def test_the_client_asks_for_the_window_and_the_sixteen_fields():
    c = client([FakeResponse(200, STROKES)])
    assert c.get(*MINUTE, logger) == STROKES
    call = c.session.calls[0]
    assert call["url"] == finland_fmi.WFS_URL
    assert call["params"] == {
        "service": "WFS", "version": "2.0.0", "request": "getFeature",
        "storedquery_id": "fmi::observations::lightning::multipointcoverage",
        "starttime": "2023-07-01T12:00:00Z", "endtime": "2023-07-01T12:01:00Z",
        "parameters": ",".join(finland_fmi.PARAMETERS),
    }
    assert "bbox" not in call["params"]
    assert c.session.headers["User-Agent"] == app.USER_AGENT


def test_a_refused_request_is_not_retried_and_says_why():
    c = client([FakeResponse(400, TOO_LONG)])
    with pytest.raises(app.DownloadError, match="HTTP 400: Too long time interval"):
        c.get(*MINUTE, logger)
    assert c.requests_made == 1


def test_a_server_error_is_retried():
    c = client([FakeResponse(502, b"<html>Bad Gateway</html>"), FakeResponse(200, EMPTY)])
    assert c.get(*MINUTE, logger) == EMPTY
    assert c.requests_made == 2


def test_a_lost_connection_is_retried():
    c = client([requests.ConnectionError("reset"), FakeResponse(200, EMPTY)])
    assert c.get(*MINUTE, logger) == EMPTY
    assert c.requests_made == 2


def test_a_client_without_a_session_makes_its_own():
    c = app.FmiClient()
    assert isinstance(c.session, requests.Session)
    assert c.session.headers["User-Agent"] == app.USER_AGENT


def test_the_client_waits_between_requests(monkeypatch):
    """The delay runs from the start of one request to the start of the next."""
    slept = []
    monkeypatch.setattr(app.time, "sleep", slept.append)
    monkeypatch.setattr(app.time, "monotonic", iter([100.0, 100.25, 101.0]).__next__)
    c = app.FmiClient(delay=1.0, session=FakeHttpSession([FakeResponse(200, EMPTY)]))
    c.get(*MINUTE, logger)
    c.get(*MINUTE, logger)
    assert slept == [0.75]


def test_the_client_gives_up_after_its_retries():
    c = client([FakeResponse(503, b"")], retries=2)
    with pytest.raises(app.DownloadError, match="after 3 attempt"):
        c.get(*MINUTE, logger)
    assert c.requests_made == 3


# --------------------------------------------------------------------------
# A month
# --------------------------------------------------------------------------

def test_a_month_is_written_as_published_with_its_sidecar(tmp_path):
    c = client(strokes_in_july_2023)
    now = datetime.datetime(2026, 11, 14, tzinfo=UTC)
    assert app.download_month(c, app.Month(2023, 7), True, now, tmp_path, logger) == 17

    lines = read_month(tmp_path / "fmi_lightning_2023-07.csv.gz")
    assert lines[0] == ",".join(app.COLUMNS)
    assert lines[1] == FIRST_ROW
    assert len(lines) == 18

    sidecar = json.loads((tmp_path / "fmi_lightning_2023-07.meta.json").read_text())
    assert (sidecar["month"], sidecar["complete"], sidecar["strokes"]) == ("2023-07", True, 17)
    assert [w["strokes"] for w in sidecar["windows"]] == [17, 0, 0, 0, 0]
    assert sidecar["windows"][0] == {"start": "2023-07-01T00:00:00Z", "end": "2023-07-08T00:00:00Z",
                                     "strokes": 17, "server_timestamp": "2026-11-14T14:50:04Z"}
    assert sidecar["windows"][-1]["end"] == "2023-08-01T00:00:00Z"
    assert sidecar["source"]["attribution"] == finland_fmi.ATTRIBUTION
    assert sidecar["columns"] == list(app.COLUMNS)
    assert sorted(path.name for path in tmp_path.iterdir()) == \
        ["fmi_lightning_2023-07.csv.gz", "fmi_lightning_2023-07.meta.json"]
    assert c.requests_made == 5


def test_a_failed_window_leaves_the_previous_files_alone(tmp_path):
    (tmp_path / "fmi_lightning_2023-07.csv.gz").write_bytes(b"old data")
    (tmp_path / "fmi_lightning_2023-07.meta.json").write_text("old sidecar")

    def third_window_refused(params):
        if params["starttime"] == "2023-07-15T00:00:00Z":
            return FakeResponse(400, UNKNOWN_PARAMETER)
        return strokes_in_july_2023(params)

    now = datetime.datetime(2026, 11, 14, tzinfo=UTC)
    with pytest.raises(app.DownloadError, match="Unknown observation parameter"):
        app.download_month(client(third_window_refused), app.Month(2023, 7), True, now,
                           tmp_path, logger)

    assert (tmp_path / "fmi_lightning_2023-07.csv.gz").read_bytes() == b"old data"
    assert (tmp_path / "fmi_lightning_2023-07.meta.json").read_text() == "old sidecar"
    assert not list(tmp_path.glob("*.part"))


def test_an_incomplete_month_stops_at_now_and_says_so(tmp_path):
    c = client(strokes_in_july_2023)
    now = datetime.datetime(2023, 7, 1, 12, 1, 0, 500000, tzinfo=UTC)
    assert app.download_month(c, app.Month(2023, 7), False, now, tmp_path, logger) == 17

    sidecar = json.loads((tmp_path / "fmi_lightning_2023-07.meta.json").read_text())
    assert sidecar["complete"] is False
    assert [(w["start"], w["end"]) for w in sidecar["windows"]] == \
        [("2023-07-01T00:00:00Z", "2023-07-01T12:01:00Z")]


# --------------------------------------------------------------------------
# A run
# --------------------------------------------------------------------------

def test_a_run_skips_what_is_on_disk_unless_overwriting(tmp_path):
    now = datetime.datetime(2023, 9, 15, tzinfo=UTC)
    args = arguments(tmp_path, 2023)

    first = client(strokes_in_july_2023)
    assert app.run(args, first, logger, now) == 0
    assert sorted(p.name for p in tmp_path.glob("*.csv.gz"))[-1] == "fmi_lightning_2023-08.csv.gz"
    assert len(list(tmp_path.glob("*.csv.gz"))) == 8
    # 31-day months are five windows, 30-day ones five, February four.
    assert first.requests_made == 7 * 5 + 4

    second = client(strokes_in_july_2023)
    app.run(args, second, logger, now)
    assert second.requests_made == 0

    third = client(strokes_in_july_2023)
    app.run(arguments(tmp_path, 2023, overwrite=True), third, logger, now)
    assert third.requests_made == first.requests_made


def test_the_month_in_progress_is_fetched_again_every_run(tmp_path):
    now = datetime.datetime(2023, 2, 10, tzinfo=UTC)
    args = arguments(tmp_path, 2023, include_current=True)
    for _ in range(2):
        c = client(strokes_in_july_2023)
        app.run(args, c, logger, now)
        # January is complete and fetched once; February, to now, every time.
        sidecar = json.loads((tmp_path / "fmi_lightning_2023-02.meta.json").read_text())
        assert sidecar["complete"] is False
    assert c.requests_made == 2
    assert json.loads((tmp_path / "fmi_lightning_2023-01.meta.json").read_text())["complete"]


def test_a_run_with_nothing_complete_yet_does_nothing(tmp_path):
    c = client(strokes_in_july_2023)
    assert app.run(arguments(tmp_path, 2023), c, logger,
                   datetime.datetime(2023, 1, 20, tzinfo=UTC)) == 0
    assert c.requests_made == 0


@pytest.mark.parametrize("sidecar", [
    pytest.param(None, id="no-sidecar"),
    pytest.param("not json", id="corrupt"),
    pytest.param(json.dumps({"month": "2023-07", "complete": False}), id="incomplete"),
    pytest.param(json.dumps({"month": "2023-06", "complete": True}), id="another-month"),
])
def test_a_month_without_a_sidecar_saying_complete_is_not_on_disk(tmp_path, sidecar):
    (tmp_path / "fmi_lightning_2023-07.csv.gz").write_bytes(b"data")
    if sidecar is not None:
        (tmp_path / "fmi_lightning_2023-07.meta.json").write_text(sidecar)
    assert app.is_downloaded(tmp_path, app.Month(2023, 7)) is False


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def test_the_last_year_defaults_to_the_first(tmp_path):
    args = arguments(tmp_path, 2018)
    assert (args.from_year, args.to_year) == (2018, 2018)


@pytest.mark.parametrize("argv", [
    pytest.param(["--from-year", "1997"], id="before-the-archive"),
    pytest.param(["--from-year", "2019", "--to-year", "2018"], id="years-reversed"),
    pytest.param(["--from-year", "2026", "--to-year", "2027"], id="future-year"),
    pytest.param(["--from-year", "2018", "--delay", "-1"], id="negative-delay"),
    pytest.param(["--from-year", "2018", "--retries", "-1"], id="negative-retries"),
    pytest.param([], id="no-year"),
])
def test_bad_arguments_are_refused(argv):
    with pytest.raises(SystemExit):
        app.parse_arguments(argv, datetime.datetime(2026, 11, 14, tzinfo=UTC))


def test_main_reports_a_refused_request_and_fails(tmp_path, monkeypatch, caplog):
    real_client = app.FmiClient

    def refusing_client(**kwargs):
        return real_client(session=FakeHttpSession([FakeResponse(400, UNKNOWN_PARAMETER)]),
                           **{**kwargs, "delay": 0.0})

    monkeypatch.setattr(app, "FmiClient", refusing_client)
    with caplog.at_level(logging.ERROR):
        status = app.main(["--from-year", "2018", "--output-dir", str(tmp_path)])
    assert status == 1
    assert "Unknown observation parameter" in caplog.text
    assert list(tmp_path.iterdir()) == []
