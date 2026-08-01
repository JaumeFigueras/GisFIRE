#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the EGIF import application.

Run against a real (ephemeral) PostgreSQL with PostGIS, through the application's
own entry point, on files built the way the service publishes them. What is being
tested is the part that is easy to get wrong and impossible to notice: that the
two steps write **different** columns of the same row, so that the second does not
undo the first, and that the fires the archive is full of — no coordinate, no
datum, an impossible UTM zone — are stored rather than dropped or misplaced.
"""

import datetime
import logging

from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.apps.imports.wildfires.spain_egif import import_wildfires as app
from src.data_model import Base
from src.providers import egif
from src.providers.egif.fire_cause import EgifFireCause
from src.providers.egif.fire_motivation import EgifFireMotivation
from src.providers.egif.ignition import EgifIgnition
from src.providers.egif.wildfire import EgifWildfire
from src.providers.egif.wildfire_report import EgifWildfireReport

from .conftest import block
from .conftest import code_list
from .conftest import excel_row
from .conftest import write_excel
from .conftest import write_xml

UTC = datetime.timezone.utc

logger = logging.getLogger("test-egif-import")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def database(postgresql):
    """An empty GisFIRE schema on an ephemeral PostgreSQL, and its URL."""
    info = postgresql.info
    url = (f"postgresql+psycopg://{info.user}:{info.password or ''}"
           f"@{info.host}:{info.port}/{info.dbname}")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    yield engine, url
    engine.dispose()


def run(url: str, *paths: Path, extra: list[str] | None = None) -> int:
    """Run the application exactly as the command line would."""
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-s", *[str(path) for path in paths],
            "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user, "--log-level", "DEBUG"]
    if password:
        argv += ["--db-password", password]
    return app.main(argv + (extra or []))


#: One Barcelona fire as the Excel publishes it, matching the real sample.
BARCELONA_EXCEL = excel_row({
    "Campania": "2020", "NumeroParte": "2020080001", "Estado": "Cerrado Revisión",
    "Comunidad": "CATALUÑA", "Provincia": "BARCELONA", "Municipio": "PIERA",
    "ComarcaIsla": "ANOIA", "EntidadMenor": "HOSTALETS", "NumeroMunicipiosAfectados": "1",
    "Hoja": "0902", "Cuadricula": "Q09", "Huso": "31",
    "CoordenadaX": "404147", "CoordenadaY": "4588697", "Datum": "ETRS89",
    "NumeroPuntosInicioIncendio": "1",
    "Detectado": "01/01/2020 16:30:00", "Extinguido": "01/01/2020 17:30:00",
    "Causa": "[100]  Rayo", "Motivacion": "-",
    "SuperficieArbolada": "2,5200", "SuperficieNoArbolada": "6,1400",
    "SuperficieTotalForestal": "8,6600", "SuperficieAgricola": "4,0600",
    "OtrasSuperficiesNoforestales": "0,0000",
    "AfectoZonasInterfazUrbanoForestal": "Si", "TipoInterfazAfectado": "13",
    "AfectoEspacioProtegido": "No", "AfectoTierrasAgrarias": "No", "AfectoZar": "No",
})


def barcelona_xml(**overrides) -> str:
    """The same fire as the XML publishes it, with its full report."""
    location = {"idcomunidad": 2, "idprovincia": 8, "idmunicipio": 91,
                "paraje": "Riu Anoia", "nummunicipiosafectados": 1,
                "puntosinicioincendio": 1, "huso": 31, "x": 404147, "y": 4588697,
                "iddatum": 2, "hoja": "0902", "cuadricula": "Q09"}
    location.update(overrides.get("location", {}))
    times = {"deteccion": "2020-01-01T16:30:00", "controlado": "2020-01-01T17:15:00",
             "extinguido": "2020-01-01T17:30:00", "llegadapmt": "2020-01-01T16:35:00"}
    times.update(overrides.get("times", {}))
    return (
        "<Pif>"
        + f"<numeroparte>{overrides.get('report_number', '2020080001')}</numeroparte>"
        + block("pif_comun", {"idpif": overrides.get("egif_id", 1205341), "anio": 2020})
        + block("pif_localizacion", location)
        + block("pif_tiempos", times)
        + block("pif_deteccion", {"iddetectadopor": 5,
                                  "primeranotificaciondesde112": "True",
                                  "iniciadojuntootros": "Ribera del río"},
                code_list("RelTipoAreaIniciadoPif", "idtipoarea", ["2"])
                + code_list("RelIniciadoJuntoAPif", "idiniciadojuntoa", ["10", "2"]))
        + block("pif_causa", {"idcausa": overrides.get("cause", 100),
                              "diastormenta": overrides.get("days_since_storm", 12),
                              "idcertidumbrecausa": 2, "idinvestigacioncausa": 1})
        + block("pif_condiciones", {"idestacionmeteorologica": "080055",
                                    "hora": "2023-12-18T16:35:00",
                                    "diasultimalluvia": 27, "tempmaxima": 8,
                                    "humrelativa": 80, "velocidadviento": 8,
                                    "direccionviento": 310},
                code_list("RelModeloCombustionPif", "idmodelocombustion", ["3", "2"]))
        + block("pif_propagacion", {},
                code_list("RelTipoFuegoPif", "idtipofuego", ["1", "3"]))
        + block("pif_perdidas", {"superficiearboladatotal": "2.5200",
                                 "superficienoarboladatotal": "6.1400",
                                 "superficienoarboladaagricola": "4.0600",
                                 "superficienoarboladaotras": "0.0000"})
        + block("pif_incidencias", {"idnivelgravedadmaximo": 0,
                                    "afectozonasinterfazurbanoforestal": "True",
                                    "afectadourbanoforestalsi": "13",
                                    "afectoespacionnatprot": "False",
                                    "afectotierraagrariarefores": "False",
                                    "afectozar": "False"})
        + "</Pif>"
    )


# --------------------------------------------------------------------------
# Step 1: the Excel
# --------------------------------------------------------------------------

def test_the_excel_step_stores_the_fire_and_seeds_the_catalogue(database, tmp_path):
    """The Excel is the only source of the cause labels, so it seeds the lookup."""
    engine, url = database
    write_excel(tmp_path / "2020-2023.xlsx", [BARCELONA_EXCEL])

    assert run(url, tmp_path / "2020-2023.xlsx") == 0

    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.report_number == "2020080001"
        assert fire.campaign == 2020
        assert fire.municipality_name == "PIERA"
        assert fire.area_ha_forest_total == pytest.approx(8.66)
        # 'Si' plus the concatenated interface flags '13' — compact and isolated.
        assert (fire.wui_affected, fire.wui_compact, fire.wui_scattered,
                fire.wui_isolated) == (True, True, False, True)

        cause = session.scalar(select(EgifFireCause))
        assert (cause.code, cause.label) == ("100", "Rayo")
        assert fire.cause_id == cause.id
        # The motivation cell is '-' on a lightning fire, which is not a code.
        assert session.scalar(select(EgifFireMotivation)) is None
        assert fire.motivation_id is None


def test_the_published_coordinate_becomes_a_point_in_4326(database, tmp_path):
    """``ST_Transform`` from the CRS the datum and zone name, done by PostGIS."""
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [BARCELONA_EXCEL])

    assert run(url, tmp_path / "e.xlsx") == 0

    with Session(engine) as session:
        ignition = session.scalar(select(EgifIgnition))
        assert (ignition.utm_zone, ignition.utm_x, ignition.utm_y) == (31, 404147.0, 4588697.0)
        assert ignition.datum == "ETRS89"
        longitude, latitude = session.execute(text(
            "SELECT ST_X(geometry), ST_Y(geometry) FROM ignition"
        )).one()
        # The lat/lon the service itself publishes for this fire.
        assert longitude == pytest.approx(1.85254312549163, abs=1e-6)
        assert latitude == pytest.approx(41.4441304358167, abs=1e-6)

        fire = session.scalar(select(EgifWildfire))
        assert fire.ignition_id == ignition.id
        assert fire.start_date_time == datetime.datetime(2020, 1, 1, 15, 30, tzinfo=UTC)
        assert fire.time_zone == egif.DEFAULT_TIME_ZONE


def test_a_canarian_fire_is_dated_in_its_own_zone(database, tmp_path):
    """An hour behind the mainland, resolved from the province and not the CCAA."""
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [excel_row({
        "Campania": "2020", "NumeroParte": "2020380001", "Provincia": "S.C. TENERIFE",
        "Comunidad": "CANARIAS", "Municipio": "ARICO", "Huso": "28",
        "CoordenadaX": "350000", "CoordenadaY": "3110000", "Datum": "REGCAN95",
        "Detectado": "01/07/2020 12:00:00", "Causa": "[100]  Rayo",
    })])

    assert run(url, tmp_path / "e.xlsx") == 0

    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.time_zone == egif.CANARY_TIME_ZONE
        # 12:00 Atlantic/Canary in July is 11:00 UTC; the mainland would be 10:00.
        assert fire.start_date_time == datetime.datetime(2020, 7, 1, 11, 0, tzinfo=UTC)


def test_a_fire_with_no_coordinate_is_stored_without_an_ignition(database, tmp_path):
    """293,710 fires of the archive publish none, nearly all of them before 2011."""
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [excel_row({
        "Campania": "2004", "NumeroParte": "2004010001", "Provincia": "ALAVA",
        "Municipio": "AMURRIO", "Huso": "30", "CoordenadaX": "\xa0",
        "CoordenadaY": "\xa0", "Datum": "  ",
        "Detectado": "03/02/2004 19:15:00", "Extinguido": "03/02/2004 19:45:00",
        "Causa": "[500]  Desconocida",
    })])

    assert run(url, tmp_path / "e.xlsx") == 0

    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.report_number == "2004010001"
        assert fire.ignition_id is None
        assert session.scalar(select(EgifIgnition)) is None


def test_a_fire_with_no_detection_instant_is_skipped_and_the_rest_committed(
        database, tmp_path, caplog):
    """The one thing a fire cannot be stored without, and the only thing."""
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [
        excel_row({"NumeroParte": "2020080002", "Campania": "2020",
                   "Detectado": "\xa0", "Causa": "[100]  Rayo"}),
        BARCELONA_EXCEL,
    ])

    with caplog.at_level(logging.ERROR):
        assert run(url, tmp_path / "e.xlsx") == 0

    assert "2020080002" in caplog.text
    with Session(engine) as session:
        stored = session.scalars(select(EgifWildfire.report_number)).all()
        assert stored == ["2020080001"]


def test_an_impossible_utm_zone_falls_back_to_the_province(database, tmp_path, caplog):
    """``huso 3`` is published, not mistyped here — seven fires in the archive.

    The point still has to land in Spain, so the zone comes from the province, and
    the substitution is reported because it is a guess and the published
    ``latitud``/``longitud`` cannot confirm it: they are computed from the same
    bad zone.
    """
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [excel_row({
        "Campania": "2011", "NumeroParte": "2011040074", "Provincia": "ALMERIA",
        "Municipio": "BERJA", "Huso": "3", "CoordenadaX": "490025",
        "CoordenadaY": "4070326", "Detectado": "01/08/2011 12:00:00",
        "Causa": "[100]  Rayo",
    })])

    with caplog.at_level(logging.WARNING):
        assert run(url, tmp_path / "e.xlsx") == 0

    assert "huso" in caplog.text and "2011040074" in caplog.text
    with Session(engine) as session:
        longitude, latitude = session.execute(text(
            "SELECT ST_X(geometry), ST_Y(geometry) FROM ignition"
        )).one()
        # Zone 30, the usual one for Almería: a point in Andalucía.
        assert -3.2 < longitude < -2.9
        assert 36.5 < latitude < 37.0
        # The published zone is still stored as published.
        assert session.scalar(select(EgifIgnition)).utm_zone == 3


@pytest.mark.parametrize("report_number,x,y,what", [
    ("2022320419", "612864", "4655", "a northing with three digits missing"),
    ("2005230258", "434047", "434047", "the easting typed into both fields"),
    ("2006490039", "697350", "46648500", "a northing with an extra digit"),
])
def test_a_coordinate_that_cannot_be_in_spain_is_refused_not_reprojected(
        database, tmp_path, caplog, report_number, x, y, what):
    """339 fires of the archive publish one, and every one lands in the sea.

    Reprojected faithfully they scatter across the Gulf of Guinea and the Atlantic,
    where nothing excludes them from a spatial query. Stored without a point they
    join the 22,855 fires that never had one — and the published numbers survive on
    the fire's own row either way, so refusing the *point* loses nothing.
    """
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [excel_row({
        "Campania": "2022", "NumeroParte": report_number, "Provincia": "OURENSE",
        "Municipio": "TRASMIRAS", "Huso": "29", "CoordenadaX": x, "CoordenadaY": y,
        "Detectado": "01/08/2022 12:00:00", "Causa": "[100]  Rayo",
    })])

    with caplog.at_level(logging.WARNING):
        assert run(url, tmp_path / "e.xlsx") == 0

    assert "not where a Spanish fire can be" in caplog.text
    assert report_number in caplog.text
    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.ignition_id is None
        assert session.scalar(select(EgifIgnition)) is None
        # Still stored, and still findable: only the point was declined.
        assert fire.report_number == report_number


def test_the_two_short_rows_of_the_real_archive_are_read_by_column(database, tmp_path):
    """A row whose empty ``Extinguido`` cell was omitted must not shift.

    Read by position the cause becomes the extinction time and the burnt area
    becomes an interface flag, and every value still looks plausible. This is the
    2008-2010 export's two fires, reproduced exactly: the cell for column R is not
    empty, it is absent.
    """
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [excel_row({
        "Campania": "2010", "NumeroParte": "2010100090", "Provincia": "CACERES",
        "Municipio": "CADALSO", "Huso": "29", "CoordenadaX": "710410",
        "CoordenadaY": "4458700", "Detectado": "06/05/2010 12:27:00",
        "Extinguido": None,  # the omitted cell
        "Causa": "[400]  Intencionado", "Motivacion": "[400]  Motivación desconocida",
        "SuperficieArbolada": "0,3500", "SuperficieNoArbolada": "0,0000",
        "SuperficieTotalForestal": "0,3500", "AfectoZar": "No",
    })])

    assert run(url, tmp_path / "e.xlsx") == 0

    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.end_date_time is None
        assert fire.cause.label == "Intencionado"
        assert fire.motivation.label == "Motivación desconocida"
        assert fire.area_ha_wooded == pytest.approx(0.35)
        assert fire.zar_affected is False


def test_a_report_number_repeated_in_one_file_is_kept_once(database, tmp_path, caplog):
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [BARCELONA_EXCEL, BARCELONA_EXCEL])

    with caplog.at_level(logging.ERROR):
        assert run(url, tmp_path / "e.xlsx") == 0

    assert "more than once" in caplog.text
    with Session(engine) as session:
        assert len(session.scalars(select(EgifWildfire)).all()) == 1


# --------------------------------------------------------------------------
# Step 2: the XML, and what it must not undo
# --------------------------------------------------------------------------

def test_both_steps_land_on_one_row_and_each_fills_its_own_columns(database, tmp_path):
    """The whole point of the two-step design.

    The Excel brings the names and the labelled cause; the XML brings the INE
    municipal code, the *paraje*, the holdover interval and the rest of the
    report. Neither blanks what the other wrote.
    """
    engine, url = database
    write_excel(tmp_path / "2020-2023.xlsx", [BARCELONA_EXCEL])
    write_xml(tmp_path / "2020-2023.xml", [barcelona_xml()])

    assert run(url, tmp_path / "2020-2023.xlsx", tmp_path / "2020-2023.xml") == 0

    with Session(engine) as session:
        fires = session.scalars(select(EgifWildfire)).all()
        assert len(fires) == 1
        fire = fires[0]

        # From the Excel, and still there after the XML step.
        assert fire.municipality_name == "PIERA"
        assert fire.ccaa_name == "CATALUÑA"
        assert fire.status == "Cerrado Revisión"
        assert fire.cause.label == "Rayo"

        # From the XML only.
        assert fire.egif_id == 1205341
        assert fire.municipality_ine_code == "08091"
        assert fire.ignition.place_name == "Riu Anoia"
        assert fire.ignition.datum_code == "2"
        assert fire.ignition.datum == "ETRS89"


def test_the_xml_step_writes_the_report_with_the_holdover_interval(database, tmp_path):
    """``diastormenta`` is published nowhere else, and is what step 2 is for."""
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [BARCELONA_EXCEL])
    write_xml(tmp_path / "e.xml", [barcelona_xml()])

    assert run(url, tmp_path / "e.xlsx", tmp_path / "e.xml") == 0

    with Session(engine) as session:
        report = session.scalar(select(EgifWildfireReport))
        assert report.days_since_storm == 12
        assert report.cause_certainty_code == "2"
        assert report.control_date_time == datetime.datetime(2020, 1, 1, 16, 15, tzinfo=UTC)
        assert report.first_ground_response_date_time == datetime.datetime(
            2020, 1, 1, 15, 35, tzinfo=UTC)
        assert report.days_since_rain == 27
        assert report.max_temperature_celsius == pytest.approx(8.0)
        # Only the time of day: the published date is the data-entry date.
        assert report.weather_observation_time == datetime.time(16, 35)
        # The four code lists, stored sorted so two equal sets compare equal.
        assert report.fuel_model_codes == ["2", "3"]
        assert report.fire_type_codes == ["1", "3"]
        assert report.start_area_type_codes == ["2"]
        assert report.started_next_to_codes == ["10", "2"]
        assert report.started_next_to_other == "Ribera del río"


def test_a_ground_fire_and_a_holdover_are_queryable_together(database, tmp_path):
    """The query the whole import exists to make possible."""
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [BARCELONA_EXCEL])
    write_xml(tmp_path / "e.xml", [barcelona_xml()])
    assert run(url, tmp_path / "e.xlsx", tmp_path / "e.xml") == 0

    with Session(engine) as session:
        found = session.scalars(
            select(EgifWildfire.report_number)
            .join(EgifWildfireReport, EgifWildfireReport.id == EgifWildfire.id)
            .join(EgifFireCause, EgifFireCause.id == EgifWildfire.cause_id)
            .where(EgifFireCause.code == egif.CAUSE_LIGHTNING)
            .where(EgifWildfireReport.days_since_storm > 0)
            .where(EgifWildfireReport.fire_type_codes.any("3"))
        ).all()
        assert found == ["2020080001"]


def test_re_running_the_excel_step_does_not_blank_what_the_xml_filled(database, tmp_path):
    """The failure this design exists to prevent, and it has to be tested for.

    A second Excel import is the normal way to pick up a revised campaign. If it
    wrote every column, it would set ``egif_id``, ``municipality_ine_code`` and
    ``place_name`` back to null, because the Excel does not publish them — and
    nothing would report it.
    """
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [BARCELONA_EXCEL])
    write_xml(tmp_path / "e.xml", [barcelona_xml()])
    assert run(url, tmp_path / "e.xlsx", tmp_path / "e.xml") == 0

    # The service revises the campaign; the Excel is exported and imported again.
    revised = dict(BARCELONA_EXCEL, SuperficieTotalForestal="9,0000",
                   Municipio="PIERA (REVISADO)")
    write_excel(tmp_path / "e2.xlsx", [revised])
    assert run(url, tmp_path / "e2.xlsx") == 0

    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.area_ha_forest_total == pytest.approx(9.0)   # updated
        assert fire.municipality_name == "PIERA (REVISADO)"      # updated
        assert fire.egif_id == 1205341                           # survived
        assert fire.municipality_ine_code == "08091"             # survived
        assert fire.ignition.place_name == "Riu Anoia"           # survived
        assert session.scalar(select(EgifWildfireReport)).days_since_storm == 12
        assert len(session.scalars(select(EgifWildfire)).all()) == 1


def test_the_xml_step_can_give_a_coordinate_to_a_fire_that_had_none(database, tmp_path):
    """An Excel-only fire with no point gains one when its XML arrives."""
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [dict(BARCELONA_EXCEL, CoordenadaX="\xa0",
                                           CoordenadaY="\xa0")])
    assert run(url, tmp_path / "e.xlsx") == 0
    with Session(engine) as session:
        assert session.scalar(select(EgifWildfire)).ignition_id is None

    write_xml(tmp_path / "e.xml", [barcelona_xml()])
    assert run(url, tmp_path / "e.xml") == 0

    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.ignition_id is not None
        assert fire.ignition.utm_x == 404147.0
        assert len(session.scalars(select(EgifIgnition)).all()) == 1


def test_the_xml_step_alone_reports_codes_it_cannot_label(database, tmp_path, caplog):
    """An XML-only database can store the fire but not read its cause."""
    engine, url = database
    write_xml(tmp_path / "e.xml", [barcelona_xml()])

    with caplog.at_level(logging.WARNING):
        assert run(url, tmp_path / "e.xml") == 0

    assert "not in the catalogue" in caplog.text
    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.report_number == "2020080001"
        assert fire.cause_id is None


def test_the_pre_2014_xml_publishes_no_datum_and_is_read_as_etrs89(database, tmp_path):
    """``iddatum`` does not exist before the 2014-2016 campaigns."""
    engine, url = database
    write_xml(tmp_path / "e.xml", [barcelona_xml(location={"iddatum": None})])

    assert run(url, tmp_path / "e.xml") == 0

    with Session(engine) as session:
        ignition = session.scalar(select(EgifIgnition))
        assert ignition.datum is None
        assert ignition.datum_code is None
        # Still placed, on the assumption every export that does say, says ETRS89.
        longitude, _ = session.execute(text("SELECT ST_X(geometry), 1 FROM ignition")).one()
        assert longitude == pytest.approx(1.85254312549163, abs=1e-6)


def test_an_unmappable_datum_code_keeps_the_code_and_reports_it(database, tmp_path, caplog):
    """``iddatum = 3`` occurs on three records and maps to nothing published."""
    engine, url = database
    write_xml(tmp_path / "e.xml", [barcelona_xml(location={"iddatum": 3})])

    with caplog.at_level(logging.WARNING):
        assert run(url, tmp_path / "e.xml") == 0

    assert "iddatum" in caplog.text
    with Session(engine) as session:
        ignition = session.scalar(select(EgifIgnition))
        assert (ignition.datum, ignition.datum_code) == (None, "3")


def test_the_forest_total_is_derived_where_the_xml_does_not_publish_it(database, tmp_path):
    """``pif_perdidas`` has the two parts and not their sum; the Excel prints it."""
    engine, url = database
    write_xml(tmp_path / "e.xml", [barcelona_xml()])
    assert run(url, tmp_path / "e.xml") == 0

    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        assert fire.area_ha_wooded == pytest.approx(2.52)
        assert fire.area_ha_non_wooded == pytest.approx(6.14)
        assert fire.area_ha_forest_total == pytest.approx(8.66)


# --------------------------------------------------------------------------
# The application around the two steps
# --------------------------------------------------------------------------

def test_a_directory_is_read_excel_first_then_xml(database, tmp_path):
    """Which is what makes the catalogue available to the XML step automatically."""
    engine, url = database
    write_excel(tmp_path / "2020-2023.xlsx", [BARCELONA_EXCEL])
    write_xml(tmp_path / "2020-2023.xml", [barcelona_xml()])

    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-d", str(tmp_path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user]
    if password:
        argv += ["--db-password", password]
    assert app.main(argv) == 0

    with Session(engine) as session:
        fire = session.scalar(select(EgifWildfire))
        # Excel-sourced and XML-sourced columns both present after one command.
        assert fire.cause.label == "Rayo"
        assert fire.municipality_ine_code == "08091"


def test_an_empty_directory_is_an_error_rather_than_a_silent_no_op(database, tmp_path):
    _, url = database
    info = url.split("//", 1)[1]
    credentials, host_part = info.split("@", 1)
    user, _, password = credentials.partition(":")
    host_port, _, name = host_part.partition("/")
    host, _, port = host_port.partition(":")
    argv = ["-d", str(tmp_path), "--db-host", host, "--db-port", port or "5432",
            "--db-name", name, "--db-user", user]
    if password:
        argv += ["--db-password", password]
    assert app.main(argv) == 1


def test_a_workbook_whose_columns_moved_is_refused(database, tmp_path):
    """Reading by position when the columns changed would import plausible nonsense."""
    _, url = database
    write_excel(tmp_path / "e.xlsx", [{"NumeroParte": "2020080001"}],
                header=("NumeroParte", "Campania"))

    assert run(url, tmp_path / "e.xlsx") == 1


def test_a_file_is_committed_only_once_it_has_been_read_whole(database, tmp_path, monkeypatch):
    """A crash half way through leaves the database exactly as it was."""
    engine, url = database
    write_excel(tmp_path / "e.xlsx", [BARCELONA_EXCEL,
                                      dict(BARCELONA_EXCEL, NumeroParte="2020080002")])

    real = app.write_batch

    def explode(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("interrupted half way through")

    monkeypatch.setattr(app, "write_batch", explode)
    assert run(url, tmp_path / "e.xlsx") == 1

    with Session(engine) as session:
        assert session.scalars(select(EgifWildfire)).all() == []
        assert session.execute(text("SELECT count(*) FROM wildfire")).scalar() == 0
