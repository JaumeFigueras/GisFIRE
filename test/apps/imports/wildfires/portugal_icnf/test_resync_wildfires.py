#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the ICNF WFS resync application.

The database is real and ephemeral; the WFS is not. A fake HTTP session returns
canned GeoServer responses, which is the only way to test the retry and paging
paths at all — a real server cannot be asked to fail on demand — and it keeps the
suite off the ICNF's machine.

The fires are seeded straight into the schema rather than run through the archive
import. What is under test is what the resync does to a row the import already
produced, and stating that starting point explicitly is clearer than deriving it.
"""

import datetime
import logging

import pytest
import requests

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.wildfires.portugal_icnf import resync_wildfires as app
from src.data_model import Base
from src.providers import icnf
from src.providers.icnf.wildfire import IcnfWildfire

logger = logging.getLogger("test-icnf-resync")

UTC = datetime.timezone.utc


# --------------------------------------------------------------------------
# A WFS that never leaves the process
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
            raise ValueError("no JSON object could be decoded")
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

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params or {}, "timeout": timeout})
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def feature(sgif, **properties):
    """One WFS feature, with the fields a fire that publishes everything has."""
    full = {
        "Cod_SGIF": sgif,
        "Cod_ANEPC": "2024010203040",
        "Ano": 2024,
        "DH_Inicio": "2024-07-15T14:23:00Z",
        "DH_1Interv": "2024-07-15T14:51:00Z",
        "DH_Fim": "2024-07-15T18:02:00Z",
        "Duracao_m": 219,
        "PI_DICOFRE": "030415",
        "PI_NUTS3": "Alto Minho",
        "PI_Distrit": "Viana do Castelo",
        "PI_Conc": "Arcos de Valdevez",
        "PI_Freg": "Soajo",
        "PI_Local": "Serra Amarela",
        "Causa_Cod": "121",
        "Causa_Tipo": "Incendiarismo",
        "Causa_Desc": "Queima de lixo",
        "AreaHaSIG": 12.5,
        "AreaHaSGIF": 12.0,
        "AreaHaPov": 5.0,
        "AreaHaMato": 7.0,
        "AreaHaAgri": 0.5,
        "Edicao": "2025-01-16T14:18:00Z",
    }
    full.update(properties)
    return {"type": "Feature", "id": f"ardida_2024.{sgif}", "geometry": None, "properties": full}


def collection(features, matched=None):
    return {
        "type": "FeatureCollection",
        "features": features,
        "numberMatched": len(features) if matched is None else matched,
        "totalFeatures": len(features) if matched is None else matched,
    }


def wfs(responses, delay=0.0, retries=2):
    """A client wired to a fake session, with the waiting turned off."""
    return app.Wfs(delay=delay, retries=retries, session=FakeHttpSession(responses))


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

@pytest.fixture
def database(postgresql):
    info = postgresql.info
    url = f"postgresql+psycopg://{info.user}:{info.password or ''}@{info.host}:{info.port}/{info.dbname}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    yield engine, info
    engine.dispose()


@pytest.fixture
def connection_arguments(database):
    _, info = database
    return ["--db-host", info.host, "--db-port", str(info.port),
            "--db-name", info.dbname, "--db-user", info.user,
            "--db-password", info.password or ""]


def seed_fire(session, provider_id, layer, sgif, published_date, precision=icnf.PRECISION_DAY):
    """Insert a fire as the archive import would have left it.

    The start is **local midnight** on the published day, which is what the import
    stores when the shapefile gave it a bare date — and exactly what the resync
    exists to replace.
    """
    wildfire_id = session.execute(text(
        "INSERT INTO wildfire (type, data_provider_id, start_date_time, time_zone) "
        "VALUES ('icnf_wildfire', :provider, "
        "        (:published || ' 00:00:00 Europe/Lisbon')::timestamptz, 'Europe/Lisbon') "
        "RETURNING id"
    ), {"provider": provider_id, "published": published_date}).scalar()
    session.execute(text(
        "INSERT INTO icnf_wildfire (id, source_layer, sgif_code, year, date_time_precision, "
        "                           area_ha_gis) "
        "VALUES (:id, :layer, :sgif, :year, :precision, 1.0)"
    ), {"id": wildfire_id, "layer": layer, "sgif": sgif,
        "year": int(published_date[:4]), "precision": precision})
    return wildfire_id


@pytest.fixture
def stored(database):
    """One modern layer with two identified fires, plus rows the resync must not touch.

    ``ardida_1975_1989`` has no identified fire at all, so the application must
    never ask the server about it; the unidentified 2024 fire is the 901 case, and
    must survive untouched.
    """
    engine, _ = database
    with Session(engine) as session:
        provider = session.execute(text(
            "INSERT INTO data_provider (name, product, full_name) "
            "VALUES (:name, :product, :full) RETURNING id"
        ), {"name": icnf.PROVIDER_NAME, "product": icnf.PROVIDER_PRODUCT,
            "full": icnf.PROVIDER_FULL_NAME}).scalar()

        seed_fire(session, provider, "ardida_2024", "SGIF-1", "2024-07-15")
        seed_fire(session, provider, "ardida_2024", "SGIF-2", "2024-08-01")
        # No identifier and no date: the source has nothing to offer for it.
        seed_fire(session, provider, "ardida_2024", None, "2024-01-01", icnf.PRECISION_YEAR)
        seed_fire(session, provider, "ardida_1975_1989", None, "1980-01-01",
                  icnf.PRECISION_YEAR)
        session.commit()
    return engine


@pytest.fixture
def args(connection_arguments):
    return app.parse_arguments(["--delay", "0", *connection_arguments])


def stored_fire(engine, sgif):
    with Session(engine) as session:
        return session.scalar(select(IcnfWildfire).where(IcnfWildfire.sgif_code == sgif))


# --------------------------------------------------------------------------
# Which layers get asked about
# --------------------------------------------------------------------------

def test_only_layers_with_identified_fires_are_resynced(stored):
    """The 1975-2013 layers have no Cod_SGIF anywhere, so there is nothing to ask."""
    with Session(stored) as session:
        assert app.layers_to_resync(session, None, logger) == ["ardida_2024"]


def test_layers_come_back_newest_first(database):
    engine, _ = database
    with Session(engine) as session:
        provider = session.execute(text(
            "INSERT INTO data_provider (name, product, full_name) VALUES ('I','A','I') RETURNING id"
        )).scalar()
        for year in (2019, 2024, 2021):
            seed_fire(session, provider, f"ardida_{year}", f"S{year}", f"{year}-07-15")
        session.commit()
        assert app.layers_to_resync(session, None, logger) == [
            "ardida_2024", "ardida_2021", "ardida_2019"
        ]


def test_nothing_imported_is_reported(database):
    engine, _ = database
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="nothing to resync"):
            app.layers_to_resync(session, None, logger)


def test_an_unknown_layer_name_is_refused(stored):
    with Session(stored) as session:
        with pytest.raises(RuntimeError, match="ardida_1999"):
            app.layers_to_resync(session, ["ardida_1999"], logger)


def test_named_layers_are_kept_newest_first(database):
    engine, _ = database
    with Session(engine) as session:
        provider = session.execute(text(
            "INSERT INTO data_provider (name, product, full_name) VALUES ('I','A','I') RETURNING id"
        )).scalar()
        for year in (2019, 2024):
            seed_fire(session, provider, f"ardida_{year}", f"S{year}", f"{year}-07-15")
        session.commit()
        assert app.layers_to_resync(session, ["ardida_2019", "ardida_2024"], logger) == [
            "ardida_2024", "ardida_2019"
        ]


# --------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------

def test_the_request_leaves_the_unidentifiable_fires_on_the_server():
    """901 fires have no identifier and nothing to give; they are never fetched."""
    client = wfs([FakeResponse(payload=collection([]))])
    app.fetch_layer(client, "ardida_2024", 5000, logger)

    parameters = client.session.calls[0]["params"]
    assert parameters["CQL_FILTER"] == "Cod_SGIF IS NOT NULL"
    assert parameters["typeName"] == "BDG:ardida_2024"
    assert parameters["sortBy"] == "DH_Inicio D"
    assert parameters["version"] == "2.0.0"


def test_the_geometry_is_not_requested():
    """Re-reading perimeters would multiply the payload to rewrite what does not change."""
    client = wfs([FakeResponse(payload=collection([]))])
    app.fetch_layer(client, "ardida_2024", 5000, logger)

    requested = client.session.calls[0]["params"]["propertyName"].split(",")
    assert "Shape" not in requested
    assert "Cod_SGIF" in requested and "DH_Inicio" in requested


def test_paging_is_followed():
    """A layer bigger than one page must not be silently truncated."""
    first = collection([feature(f"S{n}") for n in range(3)], matched=5)
    second = collection([feature(f"S{n}") for n in range(3, 5)], matched=5)
    client = wfs([FakeResponse(payload=first), FakeResponse(payload=second)])

    features = app.fetch_layer(client, "ardida_2024", 3, logger)
    assert len(features) == 5
    assert [call["params"]["startIndex"] for call in client.session.calls] == [0, 3]


def test_a_single_short_page_ends_the_loop():
    client = wfs([FakeResponse(payload=collection([feature("S1")]))])
    assert len(app.fetch_layer(client, "ardida_2024", 5000, logger)) == 1
    assert len(client.session.calls) == 1


# --------------------------------------------------------------------------
# Retry and rate limiting
# --------------------------------------------------------------------------

def test_a_server_error_is_retried_and_then_succeeds():
    client = wfs([FakeResponse(status_code=503),
                  FakeResponse(payload=collection([feature("S1")]))])
    assert len(app.fetch_layer(client, "ardida_2024", 5000, logger)) == 1
    assert len(client.session.calls) == 2


def test_a_connection_error_is_retried():
    client = wfs([requests.ConnectionError("connection reset"),
                  FakeResponse(payload=collection([]))])
    app.fetch_layer(client, "ardida_2024", 5000, logger)
    assert len(client.session.calls) == 2


def test_retries_run_out(caplog):
    client = wfs([FakeResponse(status_code=502)], retries=2)
    with pytest.raises(app.WfsError, match="after 3 attempt"):
        app.fetch_layer(client, "ardida_2024", 5000, logger)
    assert len(client.session.calls) == 3


def test_a_refusal_is_not_retried():
    """A 400 fails identically however often it is sent; retrying only delays the report."""
    client = wfs([FakeResponse(status_code=400)], retries=3)
    with pytest.raises(app.WfsError, match="HTTP 400"):
        app.fetch_layer(client, "ardida_2024", 5000, logger)
    assert len(client.session.calls) == 1


def test_a_geoserver_exception_report_is_not_mistaken_for_a_download(caplog):
    """GeoServer answers a rejected request with XML and status 200."""
    client = wfs([FakeResponse(body="<ows:ExceptionReport>bad property</ows:ExceptionReport>")],
                 retries=3)
    with pytest.raises(app.WfsError, match="not JSON"):
        app.fetch_layer(client, "ardida_2024", 5000, logger)
    assert len(client.session.calls) == 1  # not retried


def test_a_rate_limit_waits_as_long_as_the_server_asked(caplog):
    """When the server says how long to wait, that beats the exponential guess."""
    client = wfs([FakeResponse(status_code=429, headers={"Retry-After": "0"}),
                  FakeResponse(payload=collection([feature("S1")]))])
    with caplog.at_level(logging.WARNING):
        app.fetch_layer(client, "ardida_2024", 5000, logger)

    assert len(client.session.calls) == 2
    assert "Retry-After 0s" in caplog.text


@pytest.mark.parametrize("header, expected", [("30", 30.0), ("9999", app.MAX_RETRY_AFTER),
                                              ("soon", None), (None, None)])
def test_retry_after_is_read_and_capped(header, expected):
    headers = {} if header is None else {"Retry-After": header}
    assert app.Wfs._retry_after(FakeResponse(status_code=429, headers=headers)) == expected


def test_requests_are_spaced_out():
    """Nothing is known about the ICNF's limits, so the delay is enforced by the client."""
    client = wfs([FakeResponse(payload=collection([feature("S1")], matched=2)),
                  FakeResponse(payload=collection([feature("S2")], matched=2))], delay=0.25)
    started = __import__("time").monotonic()
    app.fetch_layer(client, "ardida_2024", 1, logger)
    assert __import__("time").monotonic() - started >= 0.25


def test_the_requests_made_are_counted():
    client = wfs([FakeResponse(status_code=503), FakeResponse(payload=collection([]))])
    app.fetch_layer(client, "ardida_2024", 5000, logger)
    assert client.requests_made == 2


# --------------------------------------------------------------------------
# What the resync writes
# --------------------------------------------------------------------------

def resync_one_layer(engine, args, features, layer="ardida_2024"):
    """Run one layer against a canned response and commit, as the app does."""
    client = wfs([FakeResponse(payload=collection(features))])
    with Session(engine) as session:
        counts = app.resync_layer(session, client, layer, args, logger)
        session.commit()
    return counts


def test_the_published_instants_are_stored_unchanged(stored, args):
    """The WFS publishes true UTC, so there is nothing to convert — the one place in
    the project where a published datetime is stored as it arrives."""
    resync_one_layer(stored, args, [feature("SGIF-1")])

    fire = stored_fire(stored, "SGIF-1")
    assert fire.start_date_time == datetime.datetime(2024, 7, 15, 14, 23, tzinfo=UTC)
    assert fire.end_date_time == datetime.datetime(2024, 7, 15, 18, 2, tzinfo=UTC)
    assert fire.first_response_date_time == datetime.datetime(2024, 7, 15, 14, 51, tzinfo=UTC)
    assert fire.edition_date_time == datetime.datetime(2025, 1, 16, 14, 18, tzinfo=UTC)


def test_the_precision_becomes_minute(stored, args):
    assert stored_fire(stored, "SGIF-1").date_time_precision == icnf.PRECISION_DAY
    resync_one_layer(stored, args, [feature("SGIF-1")])
    assert stored_fire(stored, "SGIF-1").date_time_precision == icnf.PRECISION_MINUTE


def test_every_other_attribute_is_resynced(stored, args):
    """The archives are a snapshot; the ICNF revises records after publishing them."""
    resync_one_layer(stored, args, [feature("SGIF-1")])

    fire = stored_fire(stored, "SGIF-1")
    assert fire.anepc_code == "2024010203040"
    assert fire.duration_minutes == 219
    assert fire.dicofre_code == "030415"
    assert fire.nuts3_name == "Alto Minho"
    assert fire.district_name == "Viana do Castelo"
    assert fire.municipality_name == "Arcos de Valdevez"
    assert fire.parish_name == "Soajo"
    assert fire.place_name == "Serra Amarela"
    assert fire.area_ha_gis == pytest.approx(12.5)
    assert fire.area_ha_sgif == pytest.approx(12.0)
    assert fire.area_ha_forest_stand == pytest.approx(5.0)
    assert fire.area_ha_shrubland == pytest.approx(7.0)
    assert fire.area_ha_agricultural == pytest.approx(0.5)


def test_the_cause_is_stored_and_linked(stored, args):
    resync_one_layer(stored, args, [feature("SGIF-1")])

    with Session(stored) as session:
        fire = session.scalar(select(IcnfWildfire).where(IcnfWildfire.sgif_code == "SGIF-1"))
        assert fire.cause is not None
        assert (fire.cause.code, fire.cause.type, fire.cause.description) == (
            "121", "Incendiarismo", "Queima de lixo"
        )


def test_a_reused_cause_code_links_to_its_own_meaning(stored, args):
    """Four codes name two classifications each; joining on the code alone would
    give a fire the meaning its code had in another year."""
    resync_one_layer(stored, args, [
        feature("SGIF-1", Causa_Cod="127", Causa_Tipo="Uso do fogo",
                Causa_Desc="Queimada de sobrantes"),
        feature("SGIF-2", Causa_Cod="127", Causa_Tipo="Reacendimento",
                Causa_Desc="Reacendimento"),
    ])

    with Session(stored) as session:
        first = session.scalar(select(IcnfWildfire).where(IcnfWildfire.sgif_code == "SGIF-1"))
        second = session.scalar(select(IcnfWildfire).where(IcnfWildfire.sgif_code == "SGIF-2"))
        assert first.cause.description == "Queimada de sobrantes"
        assert second.cause.description == "Reacendimento"
        assert first.cause_id != second.cause_id


def test_a_fire_with_no_identifier_is_left_alone(stored, args):
    """The 901 case: nothing is asked for it, so nothing may happen to it."""
    with Session(stored) as session:
        before = session.execute(text(
            "SELECT w.start_date_time, i.date_time_precision, w.updated_at "
            "FROM icnf_wildfire i JOIN wildfire w ON w.id = i.id "
            "WHERE i.sgif_code IS NULL AND i.source_layer = 'ardida_2024'")).one()

    resync_one_layer(stored, args, [feature("SGIF-1")])

    with Session(stored) as session:
        after = session.execute(text(
            "SELECT w.start_date_time, i.date_time_precision, w.updated_at "
            "FROM icnf_wildfire i JOIN wildfire w ON w.id = i.id "
            "WHERE i.sgif_code IS NULL AND i.source_layer = 'ardida_2024'")).one()
    assert before == after


def test_a_fire_the_wfs_no_longer_returns_is_reported_not_deleted(stored, args):
    counts = resync_one_layer(stored, args, [feature("SGIF-1")])
    assert counts["missing"] == 1  # SGIF-2 was not returned
    assert stored_fire(stored, "SGIF-2") is not None
    assert stored_fire(stored, "SGIF-2").date_time_precision == icnf.PRECISION_DAY


def test_a_fire_the_database_does_not_have_is_reported_not_inserted(stored, args):
    counts = resync_one_layer(stored, args, [feature("SGIF-1"), feature("SGIF-NEW")])
    assert counts["unknown"] == 1
    assert stored_fire(stored, "SGIF-NEW") is None


def test_a_revised_day_is_counted_and_taken(stored, args):
    """Not a truncated time but the ICNF moving the fire, which is worth reporting."""
    counts = resync_one_layer(stored, args, [
        feature("SGIF-1", DH_Inicio="2024-07-20T14:23:00Z"),   # published day was the 15th
        feature("SGIF-2", DH_Inicio="2024-08-01T09:00:00Z"),   # same day, time recovered
    ])
    assert counts["revised"] == 1
    assert stored_fire(stored, "SGIF-1").start_date_time == datetime.datetime(
        2024, 7, 20, 14, 23, tzinfo=UTC)


def test_a_start_at_local_midnight_is_counted(stored, args):
    """Midnight is also what "no time of day" looks like; the claim is made visible."""
    counts = resync_one_layer(stored, args, [
        feature("SGIF-1", DH_Inicio="2024-07-14T23:00:00Z"),  # 00:00 Lisbon, summer
        feature("SGIF-2", DH_Inicio="2024-08-01T09:00:00Z"),
    ])
    assert counts["midnight"] == 1


def test_a_fire_the_wfs_still_has_no_date_for_keeps_its_precision(stored, args):
    resync_one_layer(stored, args, [feature("SGIF-1", DH_Inicio=None, DH_Fim=None)])
    fire = stored_fire(stored, "SGIF-1")
    assert fire.date_time_precision == icnf.PRECISION_DAY
    # And the start it already had is kept rather than nulled.
    assert fire.start_date_time is not None


def test_running_twice_changes_nothing_the_second_time(stored, args):
    """Every write is conditional, so a row already carrying the WFS values is not
    rewritten — which is what makes an interrupted run safe to restart."""
    first = resync_one_layer(stored, args, [feature("SGIF-1")])
    assert (first["dates"], first["attributes"]) == (1, 1)

    with Session(stored) as session:
        touched = session.scalar(text(
            "SELECT w.updated_at FROM wildfire w JOIN icnf_wildfire i ON i.id = w.id "
            "WHERE i.sgif_code = 'SGIF-1'"))

    second = resync_one_layer(stored, args, [feature("SGIF-1")])
    assert (second["dates"], second["attributes"]) == (0, 0)

    with Session(stored) as session:
        assert session.scalar(text(
            "SELECT w.updated_at FROM wildfire w JOIN icnf_wildfire i ON i.id = w.id "
            "WHERE i.sgif_code = 'SGIF-1'")) == touched


# --------------------------------------------------------------------------
# The run as a whole
# --------------------------------------------------------------------------

def test_the_run_reports_its_totals(stored, args, monkeypatch):
    client = wfs([FakeResponse(payload=collection([feature("SGIF-1"), feature("SGIF-2")]))])
    monkeypatch.setattr(app, "Wfs", lambda **kwargs: client)

    totals = app.resync(args, stored, logger)
    assert totals["layers"] == 1
    assert totals["fetched"] == 2
    assert totals["dates"] == 2
    assert totals["failed"] == 0


def test_the_old_layers_are_never_asked_about(stored, args, monkeypatch):
    client = wfs([FakeResponse(payload=collection([feature("SGIF-1")]))])
    monkeypatch.setattr(app, "Wfs", lambda **kwargs: client)

    app.resync(args, stored, logger)
    asked = {call["params"]["typeName"] for call in client.session.calls}
    assert asked == {"BDG:ardida_2024"}


def test_a_dry_run_changes_nothing(stored, connection_arguments, monkeypatch):
    client = wfs([FakeResponse(payload=collection([feature("SGIF-1")]))])
    monkeypatch.setattr(app, "Wfs", lambda **kwargs: client)
    dry = app.parse_arguments(["--delay", "0", "--dry-run", *connection_arguments])

    totals = app.resync(dry, stored, logger)
    assert totals["dates"] == 1               # it says what it would have done
    assert stored_fire(stored, "SGIF-1").date_time_precision == icnf.PRECISION_DAY


def test_a_failing_layer_does_not_cost_the_others(stored, args, monkeypatch, caplog):
    """One bad layer is reported and skipped; its transaction is rolled back."""
    client = wfs([FakeResponse(status_code=500)], retries=0)
    monkeypatch.setattr(app, "Wfs", lambda **kwargs: client)
    with caplog.at_level(logging.ERROR):
        totals = app.resync(args, stored, logger)

    assert totals["failed"] == 1
    assert totals["layers"] == 0
    assert stored_fire(stored, "SGIF-1").date_time_precision == icnf.PRECISION_DAY
    assert "giving up on this layer" in caplog.text


def test_main_returns_non_zero_when_a_layer_failed(stored, connection_arguments, monkeypatch):
    client = wfs([FakeResponse(status_code=500)], retries=0)
    monkeypatch.setattr(app, "Wfs", lambda **kwargs: client)
    assert app.main(["--delay", "0", *connection_arguments]) == 1


def test_main_runs_the_whole_resync(stored, connection_arguments, monkeypatch):
    client = wfs([FakeResponse(payload=collection([feature("SGIF-1")]))])
    monkeypatch.setattr(app, "Wfs", lambda **kwargs: client)
    assert app.main(["--delay", "0", *connection_arguments]) == 0
    assert stored_fire(stored, "SGIF-1").date_time_precision == icnf.PRECISION_MINUTE


def test_main_reports_missing_database_settings(monkeypatch, caplog):
    monkeypatch.delenv("GISFIRE_DB_NAME", raising=False)
    monkeypatch.delenv("GISFIRE_DB_USER", raising=False)
    assert app.main([]) == 1
    assert "No database" in caplog.text


def test_main_reports_an_empty_database(database, connection_arguments, caplog):
    assert app.main(["--delay", "0", *connection_arguments]) == 1
    assert "nothing to resync" in caplog.text


def test_defaults_are_applied():
    parsed = app.parse_arguments([])
    assert parsed.url == icnf.PROVIDER_URL
    assert parsed.delay == app.DEFAULT_DELAY == 2.0
    assert parsed.layers is None
    assert parsed.dry_run is False


def test_a_feature_with_no_identifier_is_skipped():
    """The server is asked not to send them; if one arrives anyway it cannot be keyed."""
    rows = list(app.staging_rows([feature("SGIF-1"), feature(None), {"properties": {}}, {}]))
    assert [row["cod_sgif"] for row in rows] == ["SGIF-1"]
