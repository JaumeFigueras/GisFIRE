#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The fires both Korea Forest Service report tests count.

Inserted through the ORM: what is asserted is arithmetic over known areas, classes and
dates. 2024 runs to December and is complete; 2025 ends in September, as the real
release does, and is partial. Every fire cause occurs except ``natural``, which no
Korean fire has, and one 2025 fire is a rekindle — ``unknown`` in the shared table
though it has a class of its own.
"""

import datetime

import pytest

from src.data_model.data_provider import DataProvider
from src.providers import south_korea_kfs
from src.providers.south_korea_kfs.wildfire import KfsWildfire

#: (local start, province, area, class, suspected).
FIRES = [
    (datetime.datetime(2024, 3, 2, 13, 0), "경기", 0.5, "visitor", False),
    (datetime.datetime(2024, 7, 9, 15, 0), "강원", 2.0, "lightning", False),
    (datetime.datetime(2024, 12, 30, 23, 30), "경북", 10.0, "unknown", True),
    (datetime.datetime(2025, 3, 22, 11, 25), "경북", 100.0, "agricultural_burning", True),
    (datetime.datetime(2025, 9, 11, 16, 13), "경북", 1.0, "rekindle", False),
]

SEOUL = datetime.timezone(datetime.timedelta(hours=9))


@pytest.fixture
def fires(db_session):
    """The five fires above, stored."""
    provider = DataProvider(name=south_korea_kfs.PROVIDER_NAME,
                            product=south_korea_kfs.PROVIDER_PRODUCT,
                            full_name=south_korea_kfs.PROVIDER_FULL_NAME,
                            url=south_korea_kfs.PROVIDER_URL)
    db_session.add(provider)
    for row, (start, province, area, cause_class, suspected) in enumerate(FIRES, start=2):
        db_session.add(KfsWildfire(
            data_provider=provider,
            start_date_time=start.replace(tzinfo=SEOUL),
            time_zone=south_korea_kfs.DEFAULT_TIME_ZONE,
            year=start.year, source_file="test.csv", source_row=row,
            office_name=province, office_name_rr=south_korea_kfs.romanize(province),
            province_name=province, province_name_rr=south_korea_kfs.romanize(province),
            cause_detail="기타(직접입력)", cause_text="text", cause_text_en="text",
            cause_class=cause_class, fire_cause=south_korea_kfs.fire_cause(cause_class),
            cause_suspected=suspected, area_ha=area,
        ))
    db_session.commit()
    return db_session
