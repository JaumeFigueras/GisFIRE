#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`OchaAdminBoundary` model."""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon
from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary
from src.providers.ocha.admin_boundary import OchaAdminBoundary


@pytest.fixture
def ocha(db_session):
    """The OCHA Global International Boundaries provider row."""
    provider = DataProvider(name="OCHA", product="Global International Boundaries",
                            full_name="UN Office for the Coordination of Humanitarian Affairs")
    db_session.add(provider)
    db_session.commit()
    return provider


def a_square(x_min: float, y_min: float, x_max: float, y_max: float) -> MultiPolygon:
    """An axis-aligned square as a one-part ``MULTIPOLYGON``, in lon/lat (EPSG:4326)."""
    return MultiPolygon([Polygon([(x_min, y_min), (x_max, y_min), (x_max, y_max),
                                  (x_min, y_max), (x_min, y_min)])])


def andorra() -> MultiPolygon:
    """A stand-in for Andorra's outline, roughly its bounding box."""
    return a_square(1.41, 42.42, 1.79, 42.66)


def an_andorra_row(provider, **overrides) -> OchaAdminBoundary:
    """Andorra exactly as the boundaries layer publishes it (see the layer's ``fid`` 7)."""
    values = {
        # Generic columns, on the parent table.
        "data_provider": provider,
        "source_id": "AND-20250729",   # the layer's adm0_id
        "level": 0,
        "name": "Andorra",             # the layer's adm0_name / adm0_name1
        "geometry": func.ST_GeomFromText(andorra().wkt, 4326),
        # OCHA-specific columns.
        "source": "AND",               # adm0_src
        "name_alt": None,              # adm0_name2
        "iso_code": 20,
        "iso_2": "AD",
        "iso_3": "AND",
        "iso_3_group": "AND",
        "region1_code": 150, "region1_name": "Europe",
        "region2_code": 39, "region2_name": "Southern Europe",
        "region3_code": 39, "region3_name": "Southern Europe",
        "status_code": 1, "status_name": "State",
        "valid_date": datetime.date(2025, 2, 24),    # wld_date
        "update_date": datetime.date(2025, 7, 29),   # wld_update
        "land_source": "osm",          # wld_land
        "view": "intl",                # wld_view
        "notes": None,                 # wld_notes
    }
    values.update(overrides)
    return OchaAdminBoundary(**values)


def test_ocha_admin_boundary_persists_and_reads_back(db_session, ocha):
    db_session.add(an_andorra_row(ocha))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(OchaAdminBoundary))
    assert stored is not None
    # OCHA-specific.
    assert stored.source == "AND"
    assert stored.iso_code == 20
    assert stored.iso_2 == "AD"
    assert stored.iso_3 == "AND"
    assert stored.iso_3_group == "AND"
    assert (stored.region1_code, stored.region1_name) == (150, "Europe")
    assert (stored.region2_code, stored.region2_name) == (39, "Southern Europe")
    assert (stored.region3_code, stored.region3_name) == (39, "Southern Europe")
    assert (stored.status_code, stored.status_name) == (1, "State")
    assert stored.valid_date == datetime.date(2025, 2, 24)
    assert stored.update_date == datetime.date(2025, 7, 29)
    assert stored.land_source == "osm"
    assert stored.view == "intl"
    # Inherited from the generic model, not redefined here.
    assert stored.source_id == "AND-20250729"
    assert stored.level == 0
    assert stored.name == "Andorra"
    assert stored.data_provider.name == "OCHA"
    assert to_shape(stored.geometry).equals(andorra())


def test_joined_table_inheritance_splits_the_columns(db_session, ocha):
    """The generic columns live in ``admin_boundary``, the OCHA ones here."""
    assert OchaAdminBoundary.__tablename__ == "ocha_admin_boundary"

    columns = {column["name"] for column in inspect(db_session.get_bind()).get_columns("ocha_admin_boundary")}
    assert columns == {
        "id", "source", "name_alt", "iso_code", "iso_2", "iso_3", "iso_3_group",
        "region1_code", "region1_name", "region2_code", "region2_name",
        "region3_code", "region3_name", "status_code", "status_name",
        "valid_date", "update_date", "land_source", "view", "notes",
    }
    # The identifiers and the name belong to the parent, not to this table.
    assert {"source_id", "level", "name", "geometry"}.isdisjoint(columns)


def test_rows_share_the_primary_key_with_the_parent(db_session, ocha):
    boundary = an_andorra_row(ocha)
    db_session.add(boundary)
    db_session.commit()

    parent_ids = db_session.scalars(select(AdminBoundary.id)).all()
    assert parent_ids == [boundary.id]


def test_polymorphic_identity_is_set(db_session, ocha):
    boundary = an_andorra_row(ocha)
    db_session.add(boundary)
    db_session.commit()

    assert boundary.type == "ocha_admin_boundary"


def test_querying_the_parent_returns_the_subclass(db_session, ocha):
    """A query on ``AdminBoundary`` yields the OCHA subclass, thanks to the discriminator."""
    db_session.add(an_andorra_row(ocha))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(AdminBoundary))
    assert isinstance(stored, OchaAdminBoundary)
    assert stored.iso_3 == "AND"


def test_countries_can_be_looked_up_by_iso_3(db_session, ocha):
    """The lookup an importer does to attach a wildfire to a country."""
    db_session.add(an_andorra_row(ocha))
    db_session.add(an_andorra_row(ocha, source_id="ESP-20250729", name="España", source="ESP",
                                  iso_code=724, iso_2="ES", iso_3="ESP", iso_3_group="ESP",
                                  geometry=func.ST_GeomFromText(a_square(-9.0, 36.0, 3.0, 44.0).wkt, 4326)))
    db_session.commit()

    spain = db_session.scalar(select(OchaAdminBoundary).where(OchaAdminBoundary.iso_3 == "ESP"))
    assert spain.name == "España"


def test_the_same_country_can_be_published_once_per_view(db_session, ocha):
    """Contested boundaries appear under several ``wld_view`` values, each its own row."""
    db_session.add(an_andorra_row(ocha, source_id="AND-20250729-intl", view="intl"))
    db_session.add(an_andorra_row(ocha, source_id="AND-20250729-AND", view="AND"))
    db_session.commit()

    views = db_session.scalars(
        select(OchaAdminBoundary.view).where(OchaAdminBoundary.iso_3 == "AND").order_by(OchaAdminBoundary.view)
    ).all()
    assert views == ["AND", "intl"]


def test_name_alt_and_notes_are_optional(db_session, ocha):
    """``adm0_name2`` and ``wld_notes`` are NULL for most countries, Andorra included."""
    boundary = an_andorra_row(ocha)
    db_session.add(boundary)
    db_session.commit()

    assert boundary.name_alt is None
    assert boundary.notes is None


@pytest.mark.parametrize("missing", ["source", "iso_code", "iso_2", "iso_3", "iso_3_group",
                                     "status_code", "status_name", "valid_date", "update_date",
                                     "land_source", "view"])
def test_required_columns_are_enforced(db_session, ocha, missing):
    db_session.add(an_andorra_row(ocha, **{missing: None}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_inherited_columns_are_still_enforced(db_session, ocha):
    """``geometry`` is NOT NULL on the parent table and stays so here."""
    db_session.add(an_andorra_row(ocha, geometry=None))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_source_id_must_be_unique_within_the_provider(db_session, ocha):
    """Re-importing the same release of the layer must not duplicate the country."""
    db_session.add(an_andorra_row(ocha))
    db_session.commit()
    db_session.add(an_andorra_row(ocha))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_removes_both_rows(db_session, ocha):
    boundary = an_andorra_row(ocha)
    db_session.add(boundary)
    db_session.commit()

    db_session.delete(boundary)
    db_session.commit()

    assert db_session.scalars(select(OchaAdminBoundary)).all() == []
    assert db_session.scalars(select(AdminBoundary)).all() == []


def test_repr_before_persist():
    boundary = OchaAdminBoundary(iso_3="AND", name="Andorra")
    assert repr(boundary) == "OchaAdminBoundary(id=None, iso_3='AND', name='Andorra')"
