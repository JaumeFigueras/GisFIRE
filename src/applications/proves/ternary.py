from sqlalchemy import Column, Integer, String, ForeignKey, Table, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

# Define the tables
class WeatherStation(Base):
    __tablename__ = 'weather_stations'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    variables = relationship('Association', back_populates='weather_station')

class Variable(Base):
    __tablename__ = 'variables'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    weather_stations = relationship('Association', back_populates='variable')
    variable_states = relationship('Association', back_populates='variable', overlaps='variable, weather_stations')

class VariableState(Base):
    __tablename__ = 'variable_states'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    variables = relationship('Association', back_populates='variable_state')

class Association(Base):
    __tablename__ = 'association'
    weather_station_id = Column(Integer, ForeignKey('weather_stations.id'), primary_key=True)
    variable_id = Column(Integer, ForeignKey('variables.id'), primary_key=True)
    variable_state_id = Column(Integer, ForeignKey('variable_states.id'), primary_key=True)
    weather_station = relationship('WeatherStation', back_populates='variables')
    variable = relationship('Variable', back_populates='weather_stations')
    variable_state = relationship('VariableState', back_populates='variables')

# Create the engine and session
engine = create_engine('sqlite:///weather.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Insert elements
weather_station1 = WeatherStation(name='Station1')
variable1 = Variable(name='Temperature')
variable_state1 = VariableState(name='High')

# Establish relationships through the association table
association1 = Association(weather_station=weather_station1, variable=variable1, variable_state=variable_state1)

# Add to session and commit
session.add(weather_station1)
session.add(variable1)
session.add(variable_state1)
session.add(association1)
session.commit()

# Query to verify
stations = session.query(WeatherStation).all()
for station in stations:
    print(f'Weather Station: {station.name}')
    for assoc in station.variables:
        print(f'  Variable: {assoc.variable.name}')
        print(f'    Variable State: {assoc.variable_state.name}')
