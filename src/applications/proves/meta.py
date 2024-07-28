#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy import Integer, String, Column, select
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class ColumnsMeta(DeclarativeMeta):

    def __init__(cls, name, bases, dct):

        def property_factory(attr):
            def getter(self):
                return getattr(self, attr)

            def setter(self, value):
                setattr(self, attr, value)

            return property(getter, setter)

        if 'dynamic_columns' in dct:
            dynamic_columns = dct.pop('dynamic_columns', [])
            for col_def in dynamic_columns:
                attr_name = col_def['attr_name']
                column_name = col_def['column_name']
                column_type = col_def['column_type']
                setattr(cls, '_' + attr_name, mapped_column(column_name, String, nullable=True))
                setattr(cls, attr_name, property_factory('_' + attr_name))
        super().__init__(name, bases, dct)


Base = declarative_base(metaclass=ColumnsMeta)


class Columns(Base):

    dynamic_columns = [
        {'attr_name': 'attr1', 'column_name': 'column1', 'column_type': Integer},
        {'attr_name': 'attr2', 'column_name': 'column2', 'column_type': Integer},
        {'attr_name': 'attr3', 'column_name': 'column3', 'column_type': Integer}
    ]

    __tablename__ = 'columns'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    def __init__(self):
        super().__init__()


class Test(Base):

    __tablename__ = 'test'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class AttribsMeta(type):
    def __init__(cls, name, bases, dct):
        dynamic_attribs = dct.pop('dynamic_attribs', [])
        for col_def in dynamic_attribs:
            attr_name = col_def['attr_name']
            column_name = col_def['column_name']
            column_type = col_def['column_type']
            setattr(cls, '_' + attr_name, 12)
            super().__init__(name, bases, dct)


class Attribs(metaclass=AttribsMeta):

    dynamic_attribs = [
        {'attr_name': 'attr1', 'column_name': 'column1', 'column_type': int},
        {'attr_name': 'attr2', 'column_name': 'column2', 'column_type': int},
        {'attr_name': 'attr3', 'column_name': 'column3', 'column_type': str}
    ]

    def __init__(self):
        super().__init__()


engine = create_engine("sqlite+pysqlite:///:memory:", echo=True, future=True)
Base.metadata.create_all(engine)
session = Session(engine)



attr = Attribs()
print(attr._attr1)
print(attr._attr2)
print(attr._attr3)

test = Test()
test.id = 1

column = Columns()
column.id = 1
column.attr1 = 'Pepito'
print(column.attr1)

session.add(column)
session.commit()

data = session.execute(select(Columns).where(Columns.id == 1)).scalar_one()
print(data.id, data.attr1)
print(data._attr1)

