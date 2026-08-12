#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :class:`ConafMagnitudWildfire`, a mapped perimeter of a large Chilean fire.

This is the second of CONAF's two products, and the tests are about the three
things that makes it different from the report archive it shadows.

**The perimeter is set here and never on the report**, and the link between them
runs perimeter → report. It is written by the binder, and the schema refuses a link
that does not say how it was made: a row claiming to be a fire without saying how it
knows is not evidence of anything.

**The two areas are two measurements.** ``area_ha_mapped`` comes from the dissolved
geometry and ``area_ha_published`` is the sum of the parts' ``SUPERFICIE``; for 724
of the 743 fires they are the same number, and for the other 19 the disagreement is
the point.

And, as on the ignition, **exactly one of the two grids** — a rule that has to hold
for MULTIPOLYGONs as well as points, because Rapa Nui has a perimeter too.
"""

import datetime

import pytest

from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.wildfire import Wildfire
from src.providers import chile_conaf
from src.providers import chile_conaf_magnitud
from src.providers.chile_conaf.fire_cause import ConafFireCause
from src.providers.chile_conaf.ignition import ConafIgnition
from src.providers.chile_conaf.wildfire import ConafWildfire
from src.providers.chile_conaf_magnitud.wildfire import ConafMagnitudWildfire

UTC = datetime.timezone.utc

#: A square kilometre on the mainland grid, near Concepción.
PERIMETER_32719 = ("SRID=32719;MULTIPOLYGON(((670000 5920000, 671000 5920000, "
                   "671000 5921000, 670000 5921000, 670000 5920000)))")

#: The same fire in EPSG:4326, near enough for a test that never compares the two.
PERIMETER_4326 = ("SRID=4326;MULTIPOLYGON(((-73.05 -36.83, -73.04 -36.83, "
                  "-73.04 -36.82, -73.05 -36.82, -73.05 -36.83)))")

#: The one Easter Island perimeter's grid.
PERIMETER_32712 = ("SRID=32712;MULTIPOLYGON(((660000 6997000, 661000 6997000, "
                   "661000 6998000, 660000 6998000, 660000 6997000)))")

POINT_4326 = "SRID=4326;POINT(-73.045 -36.825)"
POINT_32719 = "SRID=32719;POINT(670500 5920500)"


@pytest.fixture
def provider(db_session):
    """The perimeter product — a second DataProvider under the same agency name."""
    provider = DataProvider(name=chile_conaf.PROVIDER_NAME,
                            product=chile_conaf_magnitud.PROVIDER_PRODUCT,
                            full_name=chile_conaf.PROVIDER_FULL_NAME,
                            url=chile_conaf_magnitud.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def report_provider(db_session):
    provider = DataProvider(name=chile_conaf.PROVIDER_NAME,
                            product=chile_conaf.PROVIDER_PRODUCT,
                            full_name=chile_conaf.PROVIDER_FULL_NAME,
                            url=chile_conaf.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def report(db_session, report_provider):
    """One report of the same fire, in the other product."""
    ignition = ConafIgnition(
        data_provider=report_provider, season_start_year=2016, number=402,
        region_code="08", geometry=POINT_4326, geometry_utm19s=POINT_32719,
        date_time=datetime.datetime(2017, 1, 18, 15, 50, tzinfo=UTC),
        time_zone=chile_conaf.DEFAULT_TIME_ZONE)
    db_session.add(ignition)
    db_session.flush()
    report = ConafWildfire(
        data_provider=report_provider, ignition_id=ignition.id, season="2016-2017",
        season_start_year=2016, number=402, name="SAN GUILLERMO",
        region_code="08", date_time_precision=chile_conaf.PRECISION_MINUTE,
        area_ha_total=327.5, area_totals_agree=True,
        start_date_time=datetime.datetime(2017, 1, 18, 15, 50, tzinfo=UTC),
        time_zone=chile_conaf.DEFAULT_TIME_ZONE)
    db_session.add(report)
    db_session.commit()
    return report


def a_perimeter(provider, **overrides) -> ConafMagnitudWildfire:
    """One dissolved fire, with everything the perimeter archive publishes."""
    values = {
        "data_provider": provider,
        "season": "2016-2017",
        "season_start_year": 2016,
        "number": 402,
        "name": "SAN GUILLERMO",
        "region": "Biobío",
        "province": "Concepción",
        "commune": "Tomé",
        "region_code": "08",
        "province_code": "081",
        "commune_code": "08111",
        "cause_published": "2.1.11. Otros intencionales no clasificados",
        "area_ha_mapped": 327.8,
        "area_ha_published": 327.5,
        "part_count": 1,
        "date_time_precision": chile_conaf.PRECISION_MINUTE,
        "perimeter": PERIMETER_4326,
        "perimeter_utm19s": PERIMETER_32719,
        "perimeter_utm12s": None,
        "start_date_time": datetime.datetime(2017, 1, 18, 15, 50, tzinfo=UTC),
        "end_date_time": datetime.datetime(2017, 1, 25, 12, 0, tzinfo=UTC),
        "time_zone": chile_conaf.DEFAULT_TIME_ZONE,
    }
    values.update(overrides)
    return ConafMagnitudWildfire(**values)


# --------------------------------------------------------------------------
# The provider constants
# --------------------------------------------------------------------------

def test_the_two_products_share_the_agency_name_and_differ_by_product():
    """One agency, one incident record, two published products — the NBAC/NFDB shape.

    A query over ``wildfire`` filtered only by provider *name* therefore counts 743
    Chilean fires twice; it has to filter by ``data_provider_id`` or by the
    polymorphic ``type``.
    """
    assert chile_conaf_magnitud.PROVIDER_NAME == chile_conaf.PROVIDER_NAME
    assert chile_conaf_magnitud.PROVIDER_PRODUCT != chile_conaf.PROVIDER_PRODUCT


def test_the_threshold_and_the_first_season_are_the_measured_ones():
    """The published minimum sits at 200-215 ha in every season from 2015-2016 on.

    And the perimeters start three seasons after the reports do, which is why
    :data:`~src.providers.chile_conaf_magnitud.FIRST_SEASON` is not
    :data:`~src.providers.chile_conaf.FIRST_SEASON`.
    """
    assert chile_conaf_magnitud.MAGNITUD_THRESHOLD_HA == 200.0
    assert chile_conaf_magnitud.FIRST_SEASON == 2013
    assert chile_conaf_magnitud.FIRST_SEASON > chile_conaf.FIRST_SEASON


def test_the_dissolve_key_carries_the_number_as_well_as_the_name():
    """Dissolving on the name alone merged four pairs of genuinely different fires.

    ``120_LOS MAITENES`` of 27 November 2016 and ``388_LOS MAITENES`` of 14 December
    are two fires with one name; without the number they became one, and 743 fires
    became 739.
    """
    assert chile_conaf_magnitud.DISSOLVE_KEY == ("season_start_year",
                                                 "name_normalised", "number")


@pytest.mark.parametrize("published, expected", [
    ("402 - SAN GUILLERMO", (402, "SAN GUILLERMO")),
    ("668_CANIHUAL VII", (668, "CANIHUAL VII")),
    ("37 TIL TIL", (37, "TIL TIL")),
    ("CERRO VIEJO", (None, "CERRO VIEJO")),
    ("", (None, None)),
    (None, (None, None)),
])
def test_the_number_is_split_off_the_published_name(published, expected):
    """Six of the thirteen archives embed the office's number in ``NOM_INCEN``.

    Splitting it off is what makes the binder work: ``'402 - SAN GUILLERMO'`` here
    and ``'SAN GUILLERMO'`` in the report archive are one fire, and the number is
    the strongest signal there is for finding it.
    """
    assert chile_conaf_magnitud.published_number(published) == expected


def test_a_published_number_column_wins_over_the_prefix():
    """2023-2024 publishes the number as a column, and it is the better source."""
    assert chile_conaf_magnitud.published_number("CERRO VIEJO", 402) \
        == (402, "CERRO VIEJO")
    assert chile_conaf_magnitud.published_number("CERRO VIEJO", "0") \
        == (None, "CERRO VIEJO")


def test_every_match_method_has_a_confidence_and_they_rank_as_documented():
    """The list is ordered strongest first, and the numbers have to agree with it.

    They are ordinal and not probabilities: they exist so a query can say "only
    bindings I would defend" without knowing the ladder.
    """
    assert set(chile_conaf_magnitud.MATCH_METHODS) \
        == set(chile_conaf_magnitud.MATCH_METHOD_CONFIDENCE)
    confidences = [chile_conaf_magnitud.MATCH_METHOD_CONFIDENCE[method]
                   for method in chile_conaf_magnitud.MATCH_METHODS]
    assert confidences == sorted(confidences, reverse=True)
    assert all(0.0 < value <= 1.0 for value in confidences)


def test_the_two_tie_breaks_for_a_repeated_number_rank_above_the_number_alone():
    """``(CODREG, NUMERO_REG)`` matches two reports for 93 perimeters of 2016-2017.

    The name settles 83 of them and containment 77, and both are stronger evidence
    than the pair that could not tell them apart — which is why they sit above it.
    """
    methods = chile_conaf_magnitud.MATCH_METHODS
    assert methods.index(chile_conaf_magnitud.MATCH_NUMBER_REGION_NAME_SEASON) \
        < methods.index(chile_conaf_magnitud.MATCH_NUMBER_REGION_SEASON)
    assert methods.index(chile_conaf_magnitud.MATCH_NUMBER_REGION_INSIDE_SEASON) \
        < methods.index(chile_conaf_magnitud.MATCH_NUMBER_REGION_SEASON)


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------

def test_a_perimeter_round_trips(db_session, provider):
    db_session.add(a_perimeter(provider))
    db_session.commit()

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert stored.season == "2016-2017"
    assert (stored.number, stored.name) == (402, "SAN GUILLERMO")
    assert stored.cause_published == "2.1.11. Otros intencionales no clasificados"
    assert stored.part_count == 1


def test_it_is_stored_across_the_two_tables(db_session, provider):
    db_session.add(a_perimeter(provider))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Wildfire.__table__)) == 1
    parent = db_session.scalar(select(Wildfire))
    assert parent.type == "conaf_magnitud_wildfire"
    assert isinstance(parent, ConafMagnitudWildfire)


def test_the_perimeter_is_set_here_unlike_on_the_report(db_session, provider):
    """This is the row whose ``data_provider_id`` names the archive the polygon is in."""
    db_session.add(a_perimeter(provider))
    db_session.commit()

    assert db_session.scalar(select(Wildfire)).perimeter is not None
    assert db_session.scalar(
        select(func.ST_GeometryType(Wildfire.perimeter))) == "ST_MultiPolygon"


# --------------------------------------------------------------------------
# The two grids
# --------------------------------------------------------------------------

def test_a_mainland_perimeter_keeps_its_own_crs(db_session, provider):
    db_session.add(a_perimeter(provider))
    db_session.commit()

    srids = db_session.execute(select(
        func.ST_SRID(ConafMagnitudWildfire.perimeter_utm19s),
        func.ST_SRID(Wildfire.perimeter),
    )).one()
    assert tuple(srids) == (chile_conaf.SOURCE_SRID_MAINLAND, 4326)


def test_the_one_easter_island_perimeter_lives_on_the_other_grid(db_session, provider):
    """One fire in 781 features, and it is the reason the ``_32712`` view exists."""
    db_session.add(a_perimeter(provider, perimeter_utm19s=None,
                               perimeter_utm12s=PERIMETER_32712))
    db_session.commit()

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert stored.perimeter_utm19s is None
    assert db_session.scalar(
        select(func.ST_SRID(ConafMagnitudWildfire.perimeter_utm12s))) \
        == chile_conaf.SOURCE_SRID_EASTER


def test_a_perimeter_is_in_one_grid_or_the_other(db_session, provider):
    """Both is a fire claiming to be on two grids 5,000 km apart."""
    db_session.add(a_perimeter(provider, perimeter_utm12s=PERIMETER_32712))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_perimeter_on_neither_grid_is_refused(db_session, provider):
    """The polygon as published is what this product is; a row without one is not a row."""
    db_session.add(a_perimeter(provider, perimeter_utm19s=None,
                               perimeter_utm12s=None))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# The two areas
# --------------------------------------------------------------------------

def test_the_mapped_and_the_published_area_are_two_measurements(db_session, provider):
    """``SUPERFICIE`` is the *feature's own* polygon area, not a reported burnt area.

    Which makes summing it over the parts wrong wherever the parts overlap:
    ``37_TIL TIL`` of 2016-2017 is six features each declaring 327.50 ha of what is
    one 327.8 ha fire. The mapped area comes from the union; the published one is
    kept beside it so the disagreement stays visible.
    """
    db_session.add(a_perimeter(provider, part_count=6, area_ha_mapped=327.8,
                               area_ha_published=1965.0))
    db_session.commit()

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert float(stored.area_ha_mapped) == pytest.approx(327.8)
    assert float(stored.area_ha_published) == pytest.approx(1965.0)


def test_the_mapped_area_is_not_called_area_ha(db_session, provider):
    """It is the mapped area; the reported burnt area of the same fire is elsewhere.

    :attr:`~src.providers.chile_conaf.wildfire.ConafWildfire.area_ha_total` is the
    office's figure for the fire and is a different number.
    """
    columns = set(ConafMagnitudWildfire.__table__.columns.keys())
    assert "area_ha_mapped" in columns
    assert "area_ha" not in columns
    assert "area_ha_total" not in columns


def test_a_negative_mapped_area_is_refused(db_session, provider):
    db_session.add(a_perimeter(provider, area_ha_mapped=-1.0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_fire_is_at_least_one_published_feature(db_session, provider):
    """19 of the 743 are more than one; ``668 - CANIHUAL VII`` is thirteen."""
    assert ConafMagnitudWildfire.__table__.c.part_count.nullable is False

    db_session.add(a_perimeter(provider, part_count=0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_multipart_fire_records_how_many_pieces_it_was_published_as(db_session,
                                                                      provider):
    db_session.add(a_perimeter(provider, part_count=13))
    db_session.commit()

    assert db_session.scalar(select(ConafMagnitudWildfire)).part_count == 13


# --------------------------------------------------------------------------
# The link to the report
# --------------------------------------------------------------------------

def test_an_unbound_perimeter_is_still_a_fire(db_session, provider):
    """The reason the two products are imported independently.

    A perimeter the binder cannot place is evidence a fire was mapped, and losing it
    because no report could be found would be losing published data.
    """
    db_session.add(a_perimeter(provider))
    db_session.commit()

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert stored.conaf_wildfire_id is None
    assert stored.match_method is None and stored.match_confidence is None


def test_a_bound_perimeter_carries_the_report_and_how_it_was_found(db_session,
                                                                   provider, report):
    method = chile_conaf_magnitud.MATCH_NUMBER_REGION_NAME_SEASON
    db_session.add(a_perimeter(
        provider, conaf_wildfire_id=report.id, match_method=method,
        match_confidence=chile_conaf_magnitud.MATCH_METHOD_CONFIDENCE[method],
        matched_at=datetime.datetime(2026, 8, 11, 12, 0, tzinfo=UTC)))
    db_session.commit()

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert isinstance(stored.conaf_wildfire, ConafWildfire)
    assert stored.conaf_wildfire.name == "SAN GUILLERMO"
    assert stored.match_confidence == pytest.approx(0.98)


def test_a_link_without_its_explanation_is_refused(db_session, provider, report):
    """A row that says which fire it is without saying how it knows is not evidence."""
    db_session.add(a_perimeter(provider, conaf_wildfire_id=report.id,
                               match_method=None))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_an_explanation_without_a_link_is_refused_too(db_session, provider):
    db_session.add(a_perimeter(
        provider, conaf_wildfire_id=None,
        match_method=chile_conaf_magnitud.MATCH_NAME_SEASON))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("method", chile_conaf_magnitud.MATCH_METHODS)
def test_every_documented_match_method_is_accepted(db_session, provider, report,
                                                   method):
    """The model's copy of the vocabulary and the migration's have to agree.

    ``test_the_conaf_match_method_constraint_accepts_every_method`` in
    :mod:`test.test_migrations` is the other half of the pair.
    """
    db_session.add(a_perimeter(
        provider, conaf_wildfire_id=report.id, match_method=method,
        match_confidence=chile_conaf_magnitud.MATCH_METHOD_CONFIDENCE[method]))
    db_session.commit()

    assert db_session.scalar(select(ConafMagnitudWildfire)).match_method == method


def test_a_method_outside_the_documented_eight_is_refused(db_session, provider,
                                                          report):
    db_session.add(a_perimeter(provider, conaf_wildfire_id=report.id,
                               match_method="looked_about_right"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_link_points_from_the_perimeter_to_the_report(db_session, provider,
                                                          report):
    """The direction NBAC and REDIAM point in: the perimeter archive is the sparse one.

    743 perimeters against 95,868 reports, so a column on the report would be NULL
    on 99.2% of rows.
    """
    assert "conaf_wildfire_id" in ConafMagnitudWildfire.__table__.columns
    assert "conaf_magnitud_wildfire_id" not in ConafWildfire.__table__.columns


# --------------------------------------------------------------------------
# The cause
# --------------------------------------------------------------------------

def test_the_published_cause_is_kept_beside_the_resolved_one(db_session, provider):
    """One ``CAUSA`` column where the reports publish two, so the string is kept.

    A reader can see what the file said without joining, and the join says which
    half of the taxonomy it turned out to be.
    """
    cause = ConafFireCause(
        specific_cause="2.1.11. Otros intencionales no clasificados",
        specific_cause_code="2.1.11")
    db_session.add(cause)
    db_session.flush()
    db_session.add(a_perimeter(provider, cause_id=cause.id))
    db_session.commit()

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert stored.cause_published == "2.1.11. Otros intencionales no clasificados"
    assert stored.cause.cause is None
    assert stored.cause.specific_cause_code == "2.1.11"


def test_a_perimeter_with_no_usable_cause_has_none(db_session, provider):
    """Eighteen of the 743, thirteen of which publish the ``'0'`` token."""
    db_session.add(a_perimeter(provider, cause_published=None, cause_id=None))
    db_session.commit()

    stored = db_session.scalar(select(ConafMagnitudWildfire))
    assert stored.cause_id is None and stored.cause is None


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

@pytest.mark.parametrize("precision", chile_conaf.DATE_TIME_PRECISIONS)
def test_every_documented_precision_is_accepted(db_session, provider, precision):
    """The same vocabulary as the report archive: three of thirteen files have no dates."""
    db_session.add(a_perimeter(provider, date_time_precision=precision))
    db_session.commit()

    assert db_session.scalar(
        select(ConafMagnitudWildfire)).date_time_precision == precision


def test_a_precision_outside_the_documented_three_is_refused(db_session, provider):
    db_session.add(a_perimeter(provider, date_time_precision="approximate"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# Nothing identifies a fire
# --------------------------------------------------------------------------

def test_the_table_constrains_no_identifier(db_session):
    """There is no ``GID`` and no key; the dissolve is the import's doing, not the file's."""
    unique = [c for c in ConafMagnitudWildfire.__table__.constraints
              if c.__class__.__name__ == "UniqueConstraint"]
    assert unique == []
    assert not any(column.unique
                   for column in ConafMagnitudWildfire.__table__.columns)


# --------------------------------------------------------------------------
# The schema as built
# --------------------------------------------------------------------------

def test_the_indexes_the_queries_need_exist(db_session):
    indexes = {index["name"] for index
               in inspect(db_session.get_bind()).get_indexes("conaf_magnitud_wildfire")}
    assert {"ix_conaf_magnitud_wildfire_season_start_year",
            "ix_conaf_magnitud_wildfire_number",
            "ix_conaf_magnitud_wildfire_cause_id",
            "ix_conaf_magnitud_wildfire_conaf_wildfire_id",
            "idx_conaf_magnitud_wildfire_perimeter_utm19s",
            "idx_conaf_magnitud_wildfire_perimeter_utm12s"} <= indexes


def test_repr_before_persist(provider):
    assert repr(a_perimeter(provider)) == (
        "ConafMagnitudWildfire(id=None, season='2016-2017', number=402, "
        "name='SAN GUILLERMO')")
