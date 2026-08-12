#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The fires both Guatemalan reports are computed over.

Shared, because the two reports are meant to agree row for row about ``Country``,
``Year`` and ``Fires``, and a fixture per report would let them drift apart without
any test noticing.

The fires are inserted through the ORM rather than imported from a GeoJSON file: what
has to be asserted is arithmetic over known values in known years, and building that
by hand is quicker and clearer than arranging for an importer to produce it.

Eight fires carrying the five things that make these two reports different from the
other seven:

* a fire whose instant falls on the **wrong side of the UTC year boundary** —
  2025-01-01 03:00 UTC is 2024-12-31 21:00 in Guatemala — so that a report grouping on
  the UTC year would put it in the wrong one and be caught;
* two **false alarms**, one in each year, which a count of fires must leave out;
* a record with a ``NULL`` ``report_status``, standing for the four that carry no
  attributes at all — the row the obvious ``<>`` filter would silently drop;
* a fire with **no point**, so ``Located`` is not trivially equal to ``Fires``;
* ``tipo_incendio`` filled on some fires and not others, which is the real archive's
  defining property: it is absent from 89% of it.
"""

from __future__ import annotations

import datetime

import pytest

from src.data_model.data_provider import DataProvider
from src.providers import guatemala_inab
from src.providers.guatemala_inab.ignition import InabIgnition
from src.providers.guatemala_inab.wildfire import InabWildfire

UTC = datetime.timezone.utc

#: (key, instant, status, fire location, institution, channel, located, protected).
#:
#: The instants are UTC, as the source publishes them. The Guatemalan year is six
#: hours earlier, which is what ``{2025-01-01T03:00Z}`` is here to prove: it is a
#: **2024** fire.
FIRES = [
    # --- 2024 in Guatemala -------------------------------------------------
    ("2024-a", datetime.datetime(2024, 4, 1, 18, 0, tzinfo=UTC),
     guatemala_inab.STATUS_CLOSED, guatemala_inab.LOCATION_IN_FOREST,
     "conred", "telefono", True, True),
    ("2024-b", datetime.datetime(2024, 6, 15, 20, 0, tzinfo=UTC),
     guatemala_inab.STATUS_CLOSED, None,
     "conap", "telefono", True, False),
    # A false alarm: not a fire, and the only record on the radio.
    ("2024-false", datetime.datetime(2024, 8, 10, 19, 0, tzinfo=UTC),
     guatemala_inab.STATUS_FALSE, None,
     "conred", "radio", True, False),
    # 03:00 UTC on 1 January is 21:00 on 31 December in Guatemala.
    ("2024-newyear", datetime.datetime(2025, 1, 1, 3, 0, tzinfo=UTC),
     guatemala_inab.STATUS_CLOSED, guatemala_inab.LOCATION_OUT_OF_FOREST,
     "otra", "app", False, False),

    # --- 2025 in Guatemala -------------------------------------------------
    ("2025-a", datetime.datetime(2025, 3, 14, 20, 30, tzinfo=UTC),
     guatemala_inab.STATUS_CLOSED, guatemala_inab.LOCATION_IN_FOREST,
     "conred", "telefono", True, True),
    ("2025-unverified", datetime.datetime(2025, 5, 2, 21, 0, tzinfo=UTC),
     guatemala_inab.STATUS_UNVERIFIED, guatemala_inab.LOCATION_OUT_OF_FOREST,
     "conap", "personal", True, True),
    # The record that carries nothing but an identifier and a map tap.
    ("2025-bare", datetime.datetime(2025, 7, 20, 18, 30, tzinfo=UTC),
     None, None, None, None, True, False),
    ("2025-false", datetime.datetime(2025, 9, 11, 22, 0, tzinfo=UTC),
     guatemala_inab.STATUS_FALSE, guatemala_inab.LOCATION_IN_FOREST,
     "conred", "telefono", True, False),
]


@pytest.fixture
def provider(db_session):
    provider = DataProvider(name=guatemala_inab.PROVIDER_NAME,
                            product=guatemala_inab.PROVIDER_PRODUCT,
                            full_name=guatemala_inab.PROVIDER_FULL_NAME,
                            url=guatemala_inab.PROVIDER_URL)
    db_session.add(provider)
    db_session.commit()
    return provider


def store(db_session, provider, key, start, status, location, institution, channel,
          located, protected, **overrides):
    """Store one fire and, when it has a point, its ignition."""
    ignition_id = None
    if located:
        ignition = InabIgnition(
            data_provider=provider, global_id=f"{{{key}}}",
            geometry="SRID=4326;POINT(-89.5 15.0)",
            date_time=start, time_zone=guatemala_inab.DEFAULT_TIME_ZONE,
        )
        db_session.add(ignition)
        db_session.flush()
        ignition_id = ignition.id

    values = {
        "data_provider": provider,
        "global_id": f"{{{key}}}",
        "start_date_time": start,
        "time_zone": guatemala_inab.DEFAULT_TIME_ZONE,
        "report_status": status,
        "fire_location": location,
        "institution": institution,
        "report_channel": channel,
        "protected_area_name": "Reserva de la Biosfera Maya" if protected else None,
        "ignition_id": ignition_id,
    }
    values.update(overrides)
    fire = InabWildfire(**values)
    db_session.add(fire)
    return fire


@pytest.fixture
def fires(db_session, provider):
    """The eight fires above, stored."""
    for record in FIRES:
        store(db_session, provider, *record)
    db_session.commit()
    return db_session
