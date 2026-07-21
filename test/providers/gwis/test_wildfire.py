#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the :class:`GwisWildfire` model."""

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
from src.data_model.wildfire import Wildfire
from src.providers.gwis.wildfire import GwisWildfire


@pytest.fixture
def gwis(db_session):
    """The GWIS Global Wildfire Database provider row."""
    provider = DataProvider(name="GWIS", product="Global Wildfire Database",
                            full_name="Global Wildfire Information System")
    db_session.add(provider)
    db_session.commit()
    return provider


def a_multipolygon() -> MultiPolygon:
    """A two-part perimeter somewhere in Catalonia, in lon/lat (EPSG:4326)."""
    return MultiPolygon([
        Polygon([(2.0, 41.0), (2.1, 41.0), (2.1, 41.1), (2.0, 41.1), (2.0, 41.0)]),
        Polygon([(2.3, 41.3), (2.4, 41.3), (2.4, 41.4), (2.3, 41.4), (2.3, 41.3)]),
    ])


def test_gwis_wildfire_persists_and_reads_back(db_session, gwis):
    start = datetime.datetime(2024, 7, 15, 12, 30, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2024, 7, 17, 8, 0, tzinfo=datetime.timezone.utc)
    perimeter = a_multipolygon()

    db_session.add(GwisWildfire(gwis_id="ES-2024-000123", data_provider=gwis,
                                start_date_time=start, end_date_time=end,
                                perimeter=func.ST_GeomFromText(perimeter.wkt, 4326)))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(GwisWildfire))
    assert stored is not None
    assert stored.gwis_id == "ES-2024-000123"
    # Inherited from the generic model, not redefined here.
    assert stored.start_date_time == start
    assert stored.end_date_time == end
    assert stored.data_provider.name == "GWIS"
    assert to_shape(stored.perimeter).equals(perimeter)


def test_joined_table_inheritance_splits_the_columns(db_session, gwis):
    """The generic columns live in ``wildfire``, only ``gwis_id`` in ``gwis_wildfire``."""
    assert GwisWildfire.__tablename__ == "gwis_wildfire"

    columns = {column["name"] for column in inspect(db_session.get_bind()).get_columns("gwis_wildfire")}
    assert columns == {"id", "gwis_id"}


def test_rows_share_the_primary_key_with_the_parent(db_session, gwis):
    wildfire = GwisWildfire(gwis_id="ES-2024-000124", data_provider=gwis,
                            start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc))
    db_session.add(wildfire)
    db_session.commit()

    parent_ids = db_session.scalars(select(Wildfire.id)).all()
    assert parent_ids == [wildfire.id]


def test_polymorphic_identity_is_set(db_session, gwis):
    wildfire = GwisWildfire(gwis_id="ES-2024-000125", data_provider=gwis,
                            start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc))
    db_session.add(wildfire)
    db_session.commit()

    assert wildfire.type == "gwis_wildfire"


def test_querying_the_parent_returns_the_subclass(db_session, gwis):
    """A query on ``Wildfire`` yields the GWIS subclass, thanks to the discriminator."""
    db_session.add(GwisWildfire(gwis_id="ES-2024-000126", data_provider=gwis,
                                start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc)))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalar(select(Wildfire))
    assert isinstance(stored, GwisWildfire)
    assert stored.gwis_id == "ES-2024-000126"


def test_gwis_id_is_required(db_session, gwis):
    db_session.add(GwisWildfire(data_provider=gwis,
                                start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc)))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_gwis_id_is_not_unique(db_session, gwis):
    """GWIS reuses ``Id`` across genuinely different fires, so the column cannot be a key.

    359 times over the 23,299,416 fires of the published 2000-2021 files, one
    ``Id`` names two different fires — ``24935861`` is a fire in Papua New Guinea
    on 8 January 2021 and another in California on 23 February. A unique
    constraint here would make the second of each pair unimportable, so there
    isn't one. See :class:`~src.providers.gwis.wildfire.GwisWildfire`.
    """
    db_session.add(GwisWildfire(
        gwis_id="24935861", data_provider=gwis,
        start_date_time=datetime.datetime(2021, 1, 8, tzinfo=datetime.timezone.utc)))
    db_session.add(GwisWildfire(
        gwis_id="24935861", data_provider=gwis,
        start_date_time=datetime.datetime(2021, 2, 23, tzinfo=datetime.timezone.utc)))
    db_session.commit()

    both = db_session.scalars(
        select(GwisWildfire).where(GwisWildfire.gwis_id == "24935861")
    ).all()
    assert len(both) == 2
    assert both[0].id != both[1].id


def test_inherited_columns_are_still_enforced(db_session, gwis):
    """``start_date_time`` is NOT NULL on the parent table and stays so here."""
    db_session.add(GwisWildfire(gwis_id="ES-2024-000127", data_provider=gwis))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_removes_both_rows(db_session, gwis):
    wildfire = GwisWildfire(gwis_id="ES-2024-000128", data_provider=gwis,
                            start_date_time=datetime.datetime(2024, 7, 15, tzinfo=datetime.timezone.utc))
    db_session.add(wildfire)
    db_session.commit()

    db_session.delete(wildfire)
    db_session.commit()

    assert db_session.scalars(select(GwisWildfire)).all() == []
    assert db_session.scalars(select(Wildfire)).all() == []


def test_repr_before_persist():
    wildfire = GwisWildfire(gwis_id="ES-2024-000129")
    assert repr(wildfire) == "GwisWildfire(id=None, gwis_id='ES-2024-000129')"
