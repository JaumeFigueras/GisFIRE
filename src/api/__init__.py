#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

from flask import Flask
from flask import jsonify
from flask import request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL

from src.api.auth import auth
from src.data_model.user_access import UserAccess

from flask import Request
from flask_httpauth import HTTPBasicAuth
from flask import Response
from typing import Optional
from typing import Tuple

db = SQLAlchemy()


def error_response(request_obj: Request, auth_obj: HTTPBasicAuth, status_code: int,
                   message: Optional[str] = None) -> Tuple[Response, int]:
    """
    Generates an API error Response with User access information stored in the database
    :param request_obj:
    :param auth_obj:
    :param status_code:
    :param message:
    :return:
    """
    user_access = UserAccess(request_obj.remote_addr, request_obj.url, request_obj.method, dict(request_obj.values),
                             status_code, auth_obj.current_user())
    db.session.add(user_access)
    db.session.commit()
    if message is None:
        return jsonify(status_code=status_code), status_code
    else:
        return jsonify({"error": message, "status_code": status_code}), status_code


def create_app(db_connection=None, params=None):
    app = Flask(__name__, instance_relative_config=True)
    if db_connection is None:  # pragma: no cover
        # These settings are for real application with WSGI and Apache, so can't be tested in a testing environment
        host = params['GISFIRE_DB_HOST']
        port = params['GISFIRE_DB_PORT']
        database = params['GISFIRE_DB_DATABASE']
        username = params['GISFIRE_DB_USERNAME']
        password = params['GISFIRE_DB_PASSWORD']
        database_url = URL.create('postgresql+psycopg', username=username, password=password, host=host, port=port,
                                  database=database)
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    else:
        uri = "postgresql+psycopg://"
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {'creator': lambda: db_connection}
        app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    @app.errorhandler(400)
    def page_error_400(error):
        return error_response(request, auth, 400)

    @app.errorhandler(401)
    def page_error_401(error):
        return error_response(request, auth, 401)

    @app.errorhandler(403)
    def page_error_403(error):
        return error_response(request, auth, 403)

    @app.errorhandler(404)
    def page_error_404(error):
        return error_response(request, auth, 404)

    @app.errorhandler(405)
    def page_error_405(error):
        return error_response(request, auth, 405)

    @app.route('/')
    def main():
        return error_response(request, auth, 500)

    from src.api.user import user
    from src.api.lightning import lightning
    from src.api.ignition import ignition

    app.register_blueprint(user.bp)
    app.register_blueprint(lightning.bp)
    app.register_blueprint(ignition.bp)
    # app.register_blueprint(stations.bp)
    # app.register_blueprint(data.bp)

    return app
