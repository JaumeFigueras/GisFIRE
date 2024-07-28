from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import sessionmaker

# Step 1: Define the metaclass
class ColumnTypeMeta(DeclarativeMeta):
    def __init__(cls, name, bases, dct):
        if 'column_type' in dct:
            column_type = dct.pop('column_type')
            if 'dynamic_column' in dct:
                dct['dynamic_column'] = Column(column_type)
        super().__init__(name, bases, dct)

# Step 2: Create the base model using the custom metaclass
Base = declarative_base(metaclass=ColumnTypeMeta)

# Step 3: Define the models
class MyModel(Base):
    __tablename__ = 'my_model'
    id = Column(Integer, primary_key=True)
    column_type = String  # Specify the column type
    dynamic_column = None  # This will be dynamically set by the metaclass

# Step 4: Create an engine and session to use the model
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Example usage
new_instance = MyModel(dynamic_column='test')
session.add(new_instance)
session.commit()

# Query the database to verify the data
result = session.query(MyModel).first()
print(result.dynamic_column)  # Output should be 'test'




from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import sessionmaker

# Step 1: Define the extended metaclass
class ColumnTypeMeta(DeclarativeMeta):
    def __init__(cls, name, bases, dct):
        if 'column_type' in dct and 'column_name' in dct:
            column_type = dct.pop('column_type')
            column_name = dct.pop('column_name')
            dct[column_name] = Column(column_type)
        super().__init__(name, bases, dct)

# Step 2: Create the base model using the extended metaclass
Base = declarative_base(metaclass=ColumnTypeMeta)

# Step 3: Define the models
class MyModel(Base):
    __tablename__ = 'my_model'
    id = Column(Integer, primary_key=True)
    column_type = String  # Specify the column type
    column_name = 'dynamic_column'  # Specify the column name

# Step 4: Create an engine and session to use the model
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Example usage
new_instance = MyModel(dynamic_column='test')
session.add(new_instance)
session.commit()

# Query the database to verify the data
result = session.query(MyModel).first()
print(result.dynamic_column)  # Output should be 'test'

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import sessionmaker


# Step 1: Define the extended metaclass
class ColumnTypeMeta(DeclarativeMeta):
    def __init__(cls, name, bases, dct):
        dynamic_columns = dct.pop('dynamic_columns', [])
        for col_def in dynamic_columns:
            attr_name = col_def['attr_name']
            column_name = col_def['column_name']
            column_type = col_def['column_type']
            dct[attr_name] = Column(column_name, column_type)
        super().__init__(name, bases, dct)


# Step 2: Create the base model using the extended metaclass
Base = declarative_base(metaclass=ColumnTypeMeta)


# Step 3: Define the models
class MyModel(Base):
    __tablename__ = 'my_model'
    id = Column(Integer, primary_key=True)

    # Specify the dynamic columns as a list of dictionaries
    dynamic_columns = [
        {'attr_name': 'dynamic_attr1', 'column_name': 'dynamic_column1', 'column_type': String},
        {'attr_name': 'dynamic_attr2', 'column_name': 'dynamic_column2', 'column_type': Integer},
        {'attr_name': 'dynamic_attr3', 'column_name': 'dynamic_column3', 'column_type': String}
    ]


# Step 4: Create an engine and session to use the model
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Example usage
new_instance = MyModel(dynamic_attr1='test1', dynamic_attr2=42, dynamic_attr3='test3')
session.add(new_instance)
session.commit()

# Query the database to verify the data
result = session.query(MyModel).first()
print(result.dynamic_attr1)  # Output should be 'test1'
print(result.dynamic_attr2)  # Output should be 42
print(result.dynamic_attr3)  # Output should be 'test3'

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import sessionmaker


# Step 1: Define the extended metaclass
class ColumnTypeMeta(DeclarativeMeta):
    def __init__(cls, name, bases, dct):
        dynamic_columns = dct.pop('dynamic_columns', [])
        for col_def in dynamic_columns:
            attr_name = col_def['attr_name']
            column_name = col_def['column_name']
            column_type = col_def['column_type']

            # Create the column
            column = Column(column_name, column_type)
            dct[attr_name] = column

            # Create getter
            def make_getter(attr_name):
                def getter(self):
                    return getattr(self, attr_name)

                return getter

            # Create setter
            def make_setter(attr_name):
                def setter(self, value):
                    setattr(self, attr_name, value)

                return setter

            # Add getter and setter to the class
            dct[f'get_{attr_name}'] = make_getter(attr_name)
            dct[f'set_{attr_name}'] = make_setter(attr_name)

        super().__init__(name, bases, dct)


# Step 2: Create the base model using the extended metaclass
Base = declarative_base(metaclass=ColumnTypeMeta)


# Step 3: Define the models
class MyModel(Base):
    __tablename__ = 'my_model'
    id = Column(Integer, primary_key=True)

    # Specify the dynamic columns as a list of dictionaries
    dynamic_columns = [
        {'attr_name': 'dynamic_attr1', 'column_name': 'dynamic_column1', 'column_type': String},
        {'attr_name': 'dynamic_attr2', 'column_name': 'dynamic_column2', 'column_type': Integer},
        {'attr_name': 'dynamic_attr3', 'column_name': 'dynamic_column3', 'column_type': String}
    ]


# Step 4: Create an engine and session to use the model
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Example usage
new_instance = MyModel(dynamic_attr1='test1', dynamic_attr2=42, dynamic_attr3='test3')
session.add(new_instance)
session.commit()

# Query the database to verify the data
result = session.query(MyModel).first()
print(result.dynamic_attr1)  # Output should be 'test1'
print(result.dynamic_attr2)  # Output should be 42
print(result.dynamic_attr3)  # Output should be 'test3'

# Example of using getters and setters
result.set_dynamic_attr1('new_test1')
result.set_dynamic_attr2(84)
result.set_dynamic_attr3('new_test3')
session.commit()

print(result.get_dynamic_attr1())  # Output should be 'new_test1'
print(result.get_dynamic_attr2())  # Output should be 84
print(result.get_dynamic_attr3())  # Output should be 'new_test3'

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import sessionmaker


# Step 1: Define the extended metaclass
class ColumnTypeMeta(DeclarativeMeta):
    def __init__(cls, name, bases, dct):
        dynamic_columns = dct.pop('dynamic_columns', [])
        for col_def in dynamic_columns:
            attr_name = col_def['attr_name']
            column_name = col_def['column_name']
            column_type = col_def['column_type']

            # Create the column
            column = Column(column_name, column_type)
            dct[attr_name] = column

            # Create getter
            def make_getter(attr_name):
                def getter(self):
                    return getattr(self, attr_name)

                return getter

            # Create setter with validation
            def make_setter(attr_name):
                def setter(self, value):
                    if isinstance(value, str) and len(value) > 10:
                        raise ValueError(f"Value for {attr_name} cannot be longer than 10 characters")
                    setattr(self, attr_name, value)

                return setter

            # Add getter and setter to the class
            dct[f'get_{attr_name}'] = make_getter(attr_name)
            dct[f'set_{attr_name}'] = make_setter(attr_name)

        super().__init__(name, bases, dct)


# Step 2: Create the base model using the extended metaclass
Base = declarative_base(metaclass=ColumnTypeMeta)


# Step 3: Define the models
class MyModel(Base):
    __tablename__ = 'my_model'
    id = Column(Integer, primary_key=True)

    # Specify the dynamic columns as a list of dictionaries
    dynamic_columns = [
        {'attr_name': 'dynamic_attr1', 'column_name': 'dynamic_column1', 'column_type': String},
        {'attr_name': 'dynamic_attr2', 'column_name': 'dynamic_column2', 'column_type': Integer},
        {'attr_name': 'dynamic_attr3', 'column_name': 'dynamic_column3', 'column_type': String}
    ]


# Step 4: Create an engine and session to use the model
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Example usage
new_instance = MyModel(dynamic_attr1='test1', dynamic_attr2=42, dynamic_attr3='test3')
session.add(new_instance)
session.commit()

# Query the database to verify the data
result = session.query(MyModel).first()
print(result.dynamic_attr1)  # Output should be 'test1'
print(result.dynamic_attr2)  # Output should be 42
print(result.dynamic_attr3)  # Output should be 'test3'

# Example of using getters and setters with validation
try:
    result.set_dynamic_attr1('new_test1')
    result.set_dynamic_attr2(84)
    result.set_dynamic_attr3('new_test3')
    session.commit()
except ValueError as e:
    print(e)  # Output should not raise an exception as values are valid

# Attempt to set a string longer than 10 characters
try:
    result.set_dynamic_attr1('this_is_a_very_long_string')
except ValueError as e:
    print(e)  # Output: Value for dynamic_attr1 cannot be longer than 10 characters

from sqlalchemy import Column, Integer, String, create_engine, TypeEngine
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.orm import sessionmaker
from typing import Any, Dict, List, Type


# Step 1: Define the extended metaclass with type hinting
class ColumnTypeMeta(DeclarativeMeta):
    def __init__(cls: Type['Base'], name: str, bases: tuple, dct: dict):
        dynamic_columns: List[Dict[str, Any]] = dct.pop('dynamic_columns', [])
        for col_def in dynamic_columns:
            attr_name: str = col_def['attr_name']
            column_name: str = col_def['column_name']
            column_type: Type[TypeEngine] = col_def['column_type']

            # Create the column
            column: Column = Column(column_name, column_type)
            dct[attr_name] = column

            # Create getter
            def make_getter(attr_name: str):
                def getter(self) -> Any:
                    return getattr(self, attr_name)

                return getter

            # Create setter with validation
            def make_setter(attr_name: str):
                def setter(self, value: Any) -> None:
                    if isinstance(value, str) and len(value) > 10:
                        raise ValueError(f"Value for {attr_name} cannot be longer than 10 characters")
                    setattr(self, attr_name, value)

                return setter

            # Add getter and setter to the class
            dct[f'get_{attr_name}'] = make_getter(attr_name)
            dct[f'set_{attr_name}'] = make_setter(attr_name)

        super().__init__(name, bases, dct)


# Step 2: Create the base model using the extended metaclass
Base = declarative_base(metaclass=ColumnTypeMeta)


# Step 3: Define the models with type hinting
class MyModel(Base):
    __tablename__ = 'my_model'
    id: int = Column(Integer, primary_key=True)

    # Specify the dynamic columns as a list of dictionaries
    dynamic_columns: List[Dict[str, Any]] = [
        {'attr_name': 'dynamic_attr1', 'column_name': 'dynamic_column1', 'column_type': String},
        {'attr_name': 'dynamic_attr2', 'column_name': 'dynamic_column2', 'column_type': Integer},
        {'attr_name': 'dynamic_attr3', 'column_name': 'dynamic_column3', 'column_type': String}
    ]


# Step 4: Create an engine and session to use the model
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Example usage
new_instance = MyModel(dynamic_attr1='test1', dynamic_attr2=42, dynamic_attr3='test3')
session.add(new_instance)
session.commit()

# Query the database to verify the data
result = session.query(MyModel).first()
print(result.dynamic_attr1)  # Output should be 'test1'
print(result.dynamic_attr2)  # Output should be 42
print(result.dynamic_attr3)  # Output should be 'test3'

# Example of using getters and setters with validation
try:
    result.set_dynamic_attr1('new_test1')
    result.set_dynamic_attr2(84)
    result.set_dynamic_attr3('new_test3')
    session.commit()
except ValueError as e:
    print(e)  # Output should not raise an exception as values are valid

# Attempt to set a string longer than 10 characters
try:
    result.set_dynamic_attr1('this_is_a_very_long_string')
except ValueError as e:
    print(e)  # Output: Value for dynamic_attr1 cannot be longer than 10 characters

from sqlalchemy import Integer, String, create_engine, TypeEngine
from sqlalchemy.orm import declarative_base, sessionmaker, DeclarativeMeta, mapped_column
from typing import Any, Dict, List, Type


# Step 1: Define the extended metaclass with type hinting
class ColumnTypeMeta(DeclarativeMeta):
    def __init__(cls: Type['Base'], name: str, bases: tuple, dct: dict):
        dynamic_columns: List[Dict[str, Any]] = dct.pop('dynamic_columns', [])
        for col_def in dynamic_columns:
            attr_name: str = col_def['attr_name']
            column_name: str = col_def['column_name']
            column_type: Type[TypeEngine] = col_def['column_type']

            # Create the mapped column
            column = mapped_column(column_type, name=column_name)
            dct[attr_name] = column

            # Create getter
            def make_getter(attr_name: str):
                def getter(self) -> Any:
                    return getattr(self, attr_name)

                return getter

            # Create setter with validation
            def make_setter(attr_name: str):
                def setter(self, value: Any) -> None:
                    if isinstance(value, str) and len(value) > 10:
                        raise ValueError(f"Value for {attr_name} cannot be longer than 10 characters")
                    setattr(self, attr_name, value)

                return setter

            # Add getter and setter to the class
            dct[f'get_{attr_name}'] = make_getter(attr_name)
            dct[f'set_{attr_name}'] = make_setter(attr_name)

        super().__init__(name, bases, dct)


# Step 2: Create the base model using the extended metaclass
Base = declarative_base(metaclass=ColumnTypeMeta)


# Step 3: Define the models with type hinting
class MyModel(Base):
    __tablename__ = 'my_model'
    id: int = mapped_column(Integer, primary_key=True)

    # Specify the dynamic columns as a list of dictionaries
    dynamic_columns: List[Dict[str, Any]] = [
        {'attr_name': 'dynamic_attr1', 'column_name': 'dynamic_column1', 'column_type': String},
        {'attr_name': 'dynamic_attr2', 'column_name': 'dynamic_column2', 'column_type': Integer},
        {'attr_name': 'dynamic_attr3', 'column_name': 'dynamic_column3', 'column_type': String}
    ]


# Step 4: Create an engine and session to use the model
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

# Example usage
new_instance = MyModel(dynamic_attr1='test1', dynamic_attr2=42, dynamic_attr3='test3')
session.add(new_instance)
session.commit()

# Query the database to verify the data
result = session.query(MyModel).first()
print(result.dynamic_attr1)  # Output should be 'test1'
print(result.dynamic_attr2)  # Output should be 42
print(result.dynamic_attr3)  # Output should be 'test3'

# Example of using getters and setters with validation
try:
    result.set_dynamic_attr1('new_test1')
    result.set_dynamic_attr2(84)
    result.set_dynamic_attr3('new_test3')
    session.commit()
except ValueError as e:
    print(e)  # Output should not raise an exception as values are valid

# Attempt to set a string longer than 10 characters
try:
    result.set_dynamic_attr1('this_is_a_very_long_string')
except ValueError as e:
    print(e)  # Output: Value for dynamic_attr1 cannot be longer than 10 characters




#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.orm import mapped_column
from geoalchemy2 import shape

from src.geo.location_converter import LocationConverter


class LocationMeta(DeclarativeMeta):
    def __init__(cls, name, bases, dct):

        def property_factory_xy(attr, validator):
            def getter(self):
                return getattr(self, '_' + attr)

            def setter(self, value):
                if validator is not None and value is not None:
                    if validator == 'longitude':
                        if not (-180 <= value <= 180):
                            raise ValueError("Longitude out of range")
                    elif validator == 'latitude':
                        if not (-90 <= value <= 90):
                            raise ValueError("Latitude out of range")
                setattr(self, '_' + attr, value)
                self.geometry_generator_4326.generate_geometry(self)
                print("geom!")

            return property(getter, setter)

        def property_factory_geometry(attr):
            def getter(self):
                geometry = getattr(self, '_' + attr)
                if geometry is not None:
                    if isinstance(geometry, str):
                        return geometry
                    else:
                        return shape.to_shape(geometry)
                return None

            def setter(self, value):
                pass

            return property(getter, setter)

        if 'location_columns' in dct:
            location_columns = dct.pop('location_columns', [])
            for col_def in location_columns:
                attr_name = col_def['attr_name'] + '_' + str(col_def['epsg'])
                column_type = col_def['column_type']
                validator = col_def['validator'] if 'validator' in col_def else None
                setattr(cls, '_' + attr_name, mapped_column(attr_name, column_type, nullable=False))
                if attr_name.startswith(('x', 'y')):
                    setattr(cls, attr_name, property_factory_xy(attr_name, validator))
                else:
                    setattr(cls, attr_name, property_factory_geometry(attr_name))
                    setattr(cls, 'geometry_generator_' + str(col_def['epsg']),
                            LocationConverter('_x_' + str(col_def['epsg']), '_y_' + str(col_def['epsg']),  str(col_def['epsg']), '_geometry_' + str(col_def['epsg'])))

        super().__init__(name, bases, dct)


