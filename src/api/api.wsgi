import logging
import sys
sys.path.insert(0, '/home/gisfire/soft/GisFIRE/src')
from src.api import create_app

logging.basicConfig(stream=sys.stderr)


def application(environ, start_response):
    params = dict()
    params['GISFIRE_DB_HOST'] = environ['GISFIRE_DB_HOST']
    params['GISFIRE_DB_PORT'] = environ['GISFIRE_DB_PORT']
    params['GISFIRE_DB_DATABASE'] = environ['GISFIRE_DB_DATABASE']
    params['GISFIRE_DB_USERNAME'] = environ['GISFIRE_DB_USERNAME']
    params['GISFIRE_DB_PASSWORD'] = environ['GISFIRE_DB_PASSWORD']

    app = create_app(params=params)
    app.secret_key = '12345678998765431'

    return app(environ, start_response)