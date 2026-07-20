#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`AdminBoundary` model."""

import datetime

import pytest

from geoalchemy2.shape import to_shape
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.data_model.data_provider import DataProvider
from src.data_model.geography.admin_boundary import AdminBoundary


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name="OCHA", product="Global International Boundaries",
                            full_name="UN Office for the Coordination of Humanitarian Affairs")
    db_session.add(provider)
    db_session.commit()
    return provider


def a_square(x_min: float, y_min: float, x_max: float, y_max: float) -> MultiPolygon:
    """An axis-aligned square as a one-part ``MULTIPOLYGON``, in lon/lat (EPSG:4326)."""
    return MultiPolygon([Polygon([(x_min, y_min), (x_max, y_min), (x_max, y_max),
                                  (x_min, y_max), (x_min, y_min)])])


def geometry_of(multipolygon: MultiPolygon):
    return func.ST_GeomFromText(multipolygon.wkt, 4326)


def a_boundary(provider, source_id: str, level: int, name: str, geometry: MultiPolygon,
               parent: AdminBoundary | None = None) -> AdminBoundary:
    return AdminBoundary(data_provider=provider, source_id=source_id, level=level, name=name,
                         geometry=geometry_of(geometry), parent=parent)


@pytest.fixture
def nested_boundaries(db_session, provider):
    """Spain > Catalonia > Girona > Osor, as four boundaries nested in space *and* in the tree.

    The geometries are nested squares, so a spatial containment query and a walk
    of ``parent``/``children`` must agree on the hierarchy.
    """
    spain = a_boundary(provider, "ESP", 0, "España", a_square(0.0, 40.0, 4.0, 44.0))
    catalonia = a_boundary(provider, "ESP.09", 1, "Catalunya", a_square(1.0, 41.0, 3.0, 43.0), spain)
    girona = a_boundary(provider, "ESP.09.17", 2, "Girona", a_square(1.5, 41.5, 2.5, 42.5), catalonia)
    osor = a_boundary(provider, "ESP.09.17.121", 3, "Osor", a_square(1.9, 41.9, 2.1, 42.1), girona)

    db_session.add_all([spain, catalonia, girona, osor])
    db_session.commit()
    return spain, catalonia, girona, osor


def test_admin_boundary_persists_and_reads_back(db_session, provider):
    geometry = a_square(1.4, 42.4, 1.8, 42.7)
    db_session.add(AdminBoundary(data_provider=provider, source_id="AND-20250729", level=0,
                                 name="Andorra", name_en="Andorra",
                                 geometry=geometry_of(geometry)))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(AdminBoundary))
    assert stored is not None
    assert stored.id is not None  # surrogate autoincrement PK assigned by the DB
    assert stored.source_id == "AND-20250729"
    assert stored.level == 0
    assert stored.name == "Andorra"
    assert stored.name_en == "Andorra"
    assert stored.data_provider.name == "OCHA"
    assert to_shape(stored.geometry).equals(geometry)


def test_geometry_is_stored_as_multipolygon_in_4326(db_session, provider):
    db_session.add(a_boundary(provider, "AND", 0, "Andorra", a_square(1.4, 42.4, 1.8, 42.7)))
    db_session.commit()

    stored = db_session.scalar(select(AdminBoundary))
    assert db_session.scalar(select(func.ST_SRID(stored.geometry))) == 4326
    assert db_session.scalar(select(func.GeometryType(stored.geometry))) == "MULTIPOLYGON"


def test_a_country_has_no_parent(db_session, nested_boundaries):
    spain, _, _, _ = nested_boundaries
    assert spain.parent is None
    assert spain.parent_id is None
    assert spain.level == 0


def test_children_and_parent_link_the_levels(db_session, nested_boundaries):
    spain, catalonia, girona, osor = nested_boundaries

    assert spain.children == [catalonia]
    assert catalonia.parent is spain
    assert osor.parent.parent.parent is spain
    assert [boundary.level for boundary in (spain, catalonia, girona, osor)] == [0, 1, 2, 3]


def test_the_tree_survives_a_round_trip(db_session, nested_boundaries):
    """The nesting is an adjacency list in the database, not just Python state."""
    db_session.expunge_all()

    osor = db_session.scalar(select(AdminBoundary).where(AdminBoundary.name == "Osor"))
    assert [ancestor.name for ancestor in (osor.parent, osor.parent.parent, osor.parent.parent.parent)] == \
        ["Girona", "Catalunya", "España"]


def test_a_branch_can_be_walked_down_with_a_recursive_cte(db_session, nested_boundaries):
    """Depth varies per country, so descendants are fetched with a recursive CTE."""
    spain, _, _, _ = nested_boundaries

    descendants = (
        select(AdminBoundary.id, AdminBoundary.name)
        .where(AdminBoundary.id == spain.id)
        .cte(recursive=True)
    )
    descendants = descendants.union_all(
        select(AdminBoundary.id, AdminBoundary.name)
        .join(descendants, AdminBoundary.parent_id == descendants.c.id)
    )

    names = db_session.scalars(select(descendants.c.name)).all()
    assert set(names) == {"España", "Catalunya", "Girona", "Osor"}


def test_a_point_is_resolved_to_a_boundary_with_a_spatial_join(db_session, nested_boundaries):
    """The query that attributes an event to a place: containment, filtered by level."""
    point = func.ST_SetSRID(func.ST_MakePoint(2.0, 42.0), 4326)

    containing = db_session.scalars(
        select(AdminBoundary.name)
        .where(func.ST_Contains(AdminBoundary.geometry, point))
        .order_by(AdminBoundary.level)
    ).all()
    assert containing == ["España", "Catalunya", "Girona", "Osor"]

    country = db_session.scalar(
        select(AdminBoundary.name)
        .where(func.ST_Contains(AdminBoundary.geometry, point), AdminBoundary.level == 0)
    )
    assert country == "España"


def test_a_point_outside_every_boundary_resolves_to_nothing(db_session, nested_boundaries):
    point = func.ST_SetSRID(func.ST_MakePoint(-30.0, 20.0), 4326)

    assert db_session.scalars(
        select(AdminBoundary.name).where(func.ST_Contains(AdminBoundary.geometry, point))
    ).all() == []


def test_source_id_must_be_unique_within_a_provider(db_session, provider):
    """The provider's own identifier is what makes a re-import idempotent."""
    db_session.add(a_boundary(provider, "AND-20250729", 0, "Andorra", a_square(1.4, 42.4, 1.8, 42.7)))
    db_session.commit()
    db_session.add(a_boundary(provider, "AND-20250729", 0, "Andorra", a_square(1.4, 42.4, 1.8, 42.7)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_two_providers_may_use_the_same_source_id(db_session, provider):
    """Uniqueness is per provider: OSM and OCHA number their boundaries independently."""
    other = DataProvider(name="OSM", product="Administrative Boundaries", full_name="OpenStreetMap")
    db_session.add(other)
    db_session.commit()

    db_session.add(a_boundary(provider, "9407", 0, "Andorra", a_square(1.4, 42.4, 1.8, 42.7)))
    db_session.add(a_boundary(other, "9407", 0, "Andorra", a_square(1.4, 42.4, 1.8, 42.7)))
    db_session.commit()

    assert len(db_session.scalars(select(AdminBoundary)).all()) == 2


def test_name_en_is_optional(db_session, provider):
    boundary = a_boundary(provider, "ESP.09", 1, "Catalunya", a_square(1.0, 41.0, 3.0, 43.0))
    db_session.add(boundary)
    db_session.commit()

    assert boundary.name_en is None


@pytest.mark.parametrize("missing", ["source_id", "level", "name", "geometry"])
def test_required_columns_are_enforced(db_session, provider, missing):
    """A boundary without a geometry is not a boundary, so none of these is nullable."""
    values = {"source_id": "AND", "level": 0, "name": "Andorra",
              "geometry": geometry_of(a_square(1.4, 42.4, 1.8, 42.7))}
    del values[missing]

    db_session.add(AdminBoundary(data_provider=provider, **values))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_data_provider_is_required(db_session):
    db_session.add(AdminBoundary(source_id="AND", level=0, name="Andorra",
                                 geometry=geometry_of(a_square(1.4, 42.4, 1.8, 42.7))))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_data_provider_must_exist(db_session):
    db_session.add(AdminBoundary(data_provider_id=12345, source_id="AND", level=0, name="Andorra",
                                 geometry=geometry_of(a_square(1.4, 42.4, 1.8, 42.7))))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_parent_must_exist(db_session, provider):
    # Set through ``parent_id`` and never through ``parent``: assigning the
    # relationship, even as None, is what SQLAlchemy flushes into the column.
    db_session.add(AdminBoundary(data_provider=provider, source_id="ESP.09", level=1,
                                 name="Catalunya", parent_id=12345,
                                 geometry=geometry_of(a_square(1.0, 41.0, 3.0, 43.0))))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_timestamps_are_set_and_timezone_aware(db_session, provider):
    boundary = a_boundary(provider, "AND", 0, "Andorra", a_square(1.4, 42.4, 1.8, 42.7))
    db_session.add(boundary)
    db_session.commit()

    assert isinstance(boundary.created_at, datetime.datetime)
    assert isinstance(boundary.updated_at, datetime.datetime)
    assert boundary.created_at.tzinfo is not None
    assert boundary.updated_at.tzinfo is not None


def test_polymorphic_identity_is_set(db_session, provider):
    """Providers add their own attributes (and their own ID) in subclasses."""
    boundary = a_boundary(provider, "AND", 0, "Andorra", a_square(1.4, 42.4, 1.8, 42.7))
    db_session.add(boundary)
    db_session.commit()

    assert boundary.type == "admin_boundary"


def test_repr_before_persist():
    boundary = AdminBoundary(level=0, name="Andorra")
    assert repr(boundary) == "AdminBoundary(id=None, level=0, name='Andorra')"
