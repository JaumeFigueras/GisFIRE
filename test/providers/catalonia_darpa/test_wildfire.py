#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`DarpaWildfire` model and the DARPA provider constants.

Three things are worth pinning down here, and each of them is a decision that
would be invisible in the column list alone: that the natural key is the code
**and** the date rather than the code — ``303/22N`` names two fires, and a unique
constraint on the code would have merged them; that the published EPSG:25831
geometry really is stored in that CRS rather than quietly reprojected; and that
the link to EGIF is a nullable column the import never fills.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import catalonia_darpa
from src.providers import spain_egif
from src.providers.catalonia_darpa.wildfire import DarpaWildfire
from src.providers.spain_egif.wildfire import EgifWildfire

UTC = datetime.timezone.utc

#: A square kilometre in ETRS89 / UTM 31N metres, somewhere in central Catalonia.
PERIMETER_25831 = ("SRID=25831;MULTIPOLYGON(((400000 4600000, 401000 4600000, "
                   "401000 4601000, 400000 4601000, 400000 4600000)))")


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=catalonia_darpa.PROVIDER_NAME,
                            product=catalonia_darpa.PROVIDER_PRODUCT,
                            full_name=catalonia_darpa.PROVIDER_FULL_NAME,
                            url=catalonia_darpa.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def a_wildfire(provider, **overrides) -> DarpaWildfire:
    """One Catalan fire, with everything the layers publish."""
    values = {
        "data_provider": provider,
        "source_layer": "incendis2013",
        "code": "2013080287",
        "fire_date": datetime.date(2013, 7, 24),
        "year": 2013,
        "municipality_name": "Sant Mateu de Bages",
        "part_count": 1,
        "start_date_time": datetime.datetime(2013, 7, 23, 22, 0, tzinfo=UTC),
        "time_zone": catalonia_darpa.DEFAULT_TIME_ZONE,
        "perimeter": ("SRID=4326;MULTIPOLYGON(((1.8 41.8, 1.81 41.8, 1.81 41.81, "
                      "1.8 41.81, 1.8 41.8)))"),
        "perimeter_etrs89_utm31n": PERIMETER_25831,
    }
    values.update(overrides)
    return DarpaWildfire(**values)


# --------------------------------------------------------------------------
# The provider constants
# --------------------------------------------------------------------------

def test_the_layer_year_is_read_from_the_layer_name():
    assert catalonia_darpa.layer_year("incendis1986") == 1986
    assert catalonia_darpa.layer_year("incendis2024") == 2024


def test_the_two_digit_layer_is_2010():
    """``incendis10`` is the department's own name for 2010, not a local renaming."""
    assert catalonia_darpa.layer_year("incendis10") == 2010


def test_a_name_with_no_year_is_refused():
    """Including the duplicate layer, whose name is the bare prefix.

    Guessing a year for it would be worse than stopping: a file imported under the
    wrong year is a silent error, and a raised one is not.
    """
    for name in ("incendis", "incendis1", "incendis199", "ardida_2024", ""):
        with pytest.raises(ValueError):
            catalonia_darpa.layer_year(name)


def test_the_duplicate_layer_is_named_so_it_can_be_skipped():
    """``incendis.shp`` is byte-identical to ``incendis2022.shp``."""
    assert "incendis" in catalonia_darpa.DUPLICATE_LAYERS


def test_the_source_crs_is_the_catalan_grid():
    assert catalonia_darpa.SOURCE_SRID == 25831


def test_the_burnt_grid_code_is_not_zero():
    """``GRID_CODE`` is the raster class; 0 is background and is not a fire."""
    assert catalonia_darpa.GRID_CODE_BURNT == 2


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

def test_a_wildfire_round_trips(db_session, provider):
    db_session.add(a_wildfire(provider))
    db_session.commit()

    stored = db_session.scalar(select(DarpaWildfire))
    assert stored.code == "2013080287"
    assert stored.fire_date == datetime.date(2013, 7, 24)
    assert stored.year == 2013
    assert stored.municipality_name == "Sant Mateu de Bages"
    assert stored.part_count == 1


def test_it_is_stored_across_the_two_tables(db_session, provider):
    """Joined table inheritance: the generic columns in wildfire, the Catalan ones here."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 1
    assert db_session.scalar(select(func.count()).select_from(DarpaWildfire.__table__)) == 1
    parent = db_session.scalar(select(Wildfire))
    assert parent.type == "darpa_wildfire"
    assert isinstance(parent, DarpaWildfire)


def test_the_published_geometry_keeps_its_own_crs(db_session, provider):
    """25831 stored as 25831, not silently reprojected to the generic model's 4326."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    # No explicit join: the joined-inheritance mapper already reaches the parent's
    # columns from the subclass.
    srids = db_session.execute(select(
        func.ST_SRID(DarpaWildfire.perimeter_etrs89_utm31n),
        func.ST_SRID(DarpaWildfire.perimeter),
    )).one()
    assert tuple(srids) == (25831, 4326)


def test_the_published_geometry_is_metres_not_degrees(db_session, provider):
    """A square kilometre measures a square kilometre on the grid it was published on.

    This is the whole reason for keeping it: the same polygon in EPSG:4326 measures
    in square degrees and means nothing without a geodesic function.
    """
    db_session.add(a_wildfire(provider))
    db_session.commit()

    area = db_session.scalar(select(func.ST_Area(DarpaWildfire.perimeter_etrs89_utm31n)))
    assert area == pytest.approx(1_000_000.0)


# --------------------------------------------------------------------------
# The natural key
# --------------------------------------------------------------------------

def test_the_same_code_on_two_dates_is_two_fires(db_session, provider):
    """``303/22N`` is Lleida on 19 June 2022 and Figueres on 7 July. Two fires.

    The reason the unique constraint is on the pair. On the code alone this insert
    would fail and the import would have had to merge two unrelated perimeters.
    """
    db_session.add(a_wildfire(provider, source_layer="incendis2022", code="303/22N",
                              fire_date=datetime.date(2022, 6, 19), year=2022,
                              municipality_name="LLEIDA"))
    db_session.add(a_wildfire(provider, source_layer="incendis2022", code="303/22N",
                              fire_date=datetime.date(2022, 7, 7), year=2022,
                              municipality_name="FIGUERES"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(DarpaWildfire.__table__)) == 2


def test_the_same_code_on_the_same_date_is_refused(db_session, provider):
    """The pair really is a key: importing a layer twice cannot double a fire."""
    db_session.add(a_wildfire(provider))
    db_session.commit()
    db_session.add(a_wildfire(provider))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_code_is_stored_in_whichever_form_it_was_published(db_session, provider):
    """Five historical formats and one internal reference, none of them parsed."""
    published = ["178600064", "G0870016", "L89004001", "894496", "2013080287", "303/22N"]
    for index, code in enumerate(published):
        db_session.add(a_wildfire(provider, code=code,
                                  fire_date=datetime.date(2013, 7, index + 1)))
    db_session.commit()

    assert set(db_session.scalars(select(DarpaWildfire.code))) == set(published)


# --------------------------------------------------------------------------
# What a row may and may not leave out
# --------------------------------------------------------------------------

@pytest.mark.parametrize("column", ["source_layer", "code", "fire_date", "year",
                                    "municipality_name", "part_count"])
def test_the_published_attributes_are_all_required(db_session, provider, column):
    """Every burnt feature in the archive has all four, so nothing here is nullable.

    That is only true because the background polygons — which carry none of them —
    are not fires and are dropped at import. See
    :data:`~src.providers.catalonia_darpa.GRID_CODE_BURNT`.
    """
    db_session.add(a_wildfire(provider, **{column: None}))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_end_date_time_is_left_unset(db_session, provider):
    """The dataset publishes one date and does not say what it is the date of."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(Wildfire.end_date_time)) is None


def test_a_fire_may_have_no_perimeter_in_the_source_crs(db_session, provider):
    """Nullable, like the ICNF's, so the column can be backfilled rather than blocking."""
    db_session.add(a_wildfire(provider, perimeter_etrs89_utm31n=None))
    db_session.commit()

    assert db_session.scalar(select(DarpaWildfire.perimeter_etrs89_utm31n)) is None


# --------------------------------------------------------------------------
# The EGIF relation
# --------------------------------------------------------------------------

def test_the_egif_link_is_unset_by_default(db_session, provider):
    """The import never fills it; the binding application does."""
    db_session.add(a_wildfire(provider))
    db_session.commit()

    assert db_session.scalar(select(DarpaWildfire.egif_wildfire_id)) is None


def test_the_egif_link_resolves_to_the_parte(db_session, provider):
    """What the column is for: the Spanish report for the same fire.

    The code and the report number are deliberately the same string here — the
    ten-digit Catalan codes are shaped exactly like an EGIF ``report_number`` — but
    nothing in the model enforces that, and nothing in the import assumes it.
    """
    egif_provider = DataProvider(name=spain_egif.PROVIDER_NAME,
                                 product=spain_egif.PROVIDER_PRODUCT,
                                 full_name=spain_egif.PROVIDER_FULL_NAME)
    db_session.add(egif_provider)
    db_session.flush()
    parte = EgifWildfire(
        data_provider_id=egif_provider.id, report_number="2013080287", campaign=2013,
        province_ine_code="08",
        start_date_time=datetime.datetime(2013, 7, 24, 10, 0, tzinfo=UTC),
        time_zone=spain_egif.DEFAULT_TIME_ZONE)
    db_session.add(parte)
    db_session.flush()

    db_session.add(a_wildfire(provider, egif_wildfire_id=parte.id,
                              match_method="code", match_confidence=1.0))
    db_session.commit()

    stored = db_session.scalar(select(DarpaWildfire))
    assert stored.egif_wildfire.report_number == stored.code


def test_the_egif_link_must_point_at_a_real_parte(db_session, provider):
    """A foreign key, not a loose integer: a binding cannot invent a report."""
    db_session.add(a_wildfire(provider, egif_wildfire_id=999999,
                              match_method="code", match_confidence=1.0))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_egif_link_is_indexed(db_session):
    """Every join from a Catalan perimeter to its parte goes through it."""
    indexes = {index["name"] for index
               in inspect(db_session.get_bind()).get_indexes("darpa_wildfire")}
    assert "ix_darpa_wildfire_egif_wildfire_id" in indexes


def test_the_canonical_layer_name_is_four_digits():
    """One year, up to four published names, one source_layer."""
    assert catalonia_darpa.source_layer_name(2010) == "incendis2010"
    assert catalonia_darpa.source_layer_name(1994) == "incendis1994"


def test_every_published_spelling_of_a_year_gives_the_same_layer_name():
    """``incendis22.zip``, ``incendis2022.shp`` and ``incendis10`` all resolve.

    The property the replace-the-year rule depends on: two copies of one year must
    not end up under two different ``source_layer`` values.
    """
    for spelling in ("incendis2022", "incendis22"):
        assert catalonia_darpa.source_layer_name(
            catalonia_darpa.layer_year(spelling)) == "incendis2022"
    for spelling in ("incendis2010", "incendis10"):
        assert catalonia_darpa.source_layer_name(
            catalonia_darpa.layer_year(spelling)) == "incendis2010"
