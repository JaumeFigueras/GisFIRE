#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import pytz

from sqlalchemy import DateTime
from sqlalchemy import func
from sqlalchemy.orm import declared_attr
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from typing import Optional
from typing import Union


class TimeStampMixIn(object):

    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
