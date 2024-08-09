#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz

from sqlalchemy import DateTime
from sqlalchemy import func
from sqlalchemy.orm import declarative_mixin
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


@declarative_mixin
class TimeStampMixIn(object):

    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __iter__(self):
        yield 'ts', self.ts.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%S%z') if self.ts is not None else None

