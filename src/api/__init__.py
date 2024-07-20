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

db = SQLAlchemy()


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

    @app.errorhandler(401)
    def page_error_401(error):

        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values),
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=401), 401

    @app.errorhandler(404)
    def page_error_404(error):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values),
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=404), 404

    @app.errorhandler(405)
    def page_error_405(error):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values),
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=405), 405

    @app.route('/')
    def main():
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values),
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=500), 500

    # app.register_blueprint(user.bp)
    # app.register_blueprint(lightning.bp)
    # app.register_blueprint(stations.bp)
    # app.register_blueprint(data.bp)

    return app
