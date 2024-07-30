import datetime
import pytz

from dateutil.tz import tzoffset  # Do not remove, necessary for eval tzoffset in run-time

from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy.orm import declared_attr
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import synonym
from sqlalchemy.orm import declarative_mixin
from sqlalchemy.orm import DeclarativeMeta

from src.data_model.metaclass.location_metaclass import LocationMeta
from typing import Optional
from typing import List


class DateTimeMeta(LocationMeta):
    def __init__(cls, name, bases, dct):

        def property_factory(attr: str) -> property:
            def getter(self):
                return getattr(self, attr)

            def setter(self, value):
                if value is not None:
                    if value.tzinfo is None:
                        raise ValueError('Date must contain timezone information')
                    setattr(self, '_tzinfo' + attr, str(value.tzinfo))
                    setattr(self, attr, value)
                else:
                    setattr(self, '_tzinfo' + attr, None)
                    setattr(self, attr, None)

            return property(getter, setter)

        if 'attributes' in dct:
            attributes = dct.pop('attributes', [])
            for attribute in attributes:
                attribute_name = column_name = attribute['name']
                protected_attribute_name = '_' + attribute_name
                nullable = attribute['nullable']
                setattr(cls, protected_attribute_name, mapped_column(column_name, DateTime(timezone=True), nullable=nullable))
                setattr(cls, '_tzinfo' + protected_attribute_name, mapped_column('tzinfo_' + column_name, String, nullable=nullable))
                setattr(cls, attribute_name, property_factory(protected_attribute_name))

        super().__init__(name, bases, dct)

