#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import json
import dateutil.parser
import pytz

from pytz import UnknownTimeZoneError

from flask import Blueprint
from flask import jsonify, make_response
from flask import request
from flask import current_app as app
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.api import db
from src.api.auth import auth

from src.data_model.user import User
from src.data_model.user_access import UserAccess

bp = Blueprint("user", __name__, url_prefix="/v2/user")


@bp.route('/', methods=['POST'])
@bp.route('', methods=['POST'])
@auth.login_required(role='admin')
def create_user():
    """
    Creates a new user with its random token. Requests parameters can be:
      - username: A string containing the username of the new user.
      - valid_until: A string containing the date and time the user validity with
      - timezone

    :return: A new user object
    :rtype: gisfire_api.user.User
    """

    # Check that all needed parameters are present
    if (request.values is None) or not (1 <= len(request.values) <= 3):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
    if not set(request.values.keys()) <= {'valid_until', 'timezone', 'username'}:
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
    if 'username' not in request.values:
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
    if 'timezone' in request.values and 'valid_until' not in request.values:
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422

    # Create the local variables for the user and convert them to proper types
    username = request.values['username']
    try:
        if 'valid_until' in request.values:
            valid_until = dateutil.parser.isoparse(request.values['valid_until'])
            if valid_until.tzinfo is None:
                if 'timezone' in request.values:
                    valid_until = pytz.timezone(request.values['timezone']).localize(valid_until)
                else:
                    valid_until = datetime.datetime(year=valid_until.year, month=valid_until.month, day=valid_until.day, hour=valid_until.hour, minute=valid_until.minute, second=valid_until.second, tzinfo=pytz.UTC)
            else:
                if 'timezone' in request.values:
                    raise ValueError("Timezone provided with timezone aware date")
        else:
            valid_until = None
    except (ValueError, UnknownTimeZoneError):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422

    try:
        user = User(username=username, valid_until=valid_until)
        db.session.add(user)
        db.session.commit()
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 200,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(dict(user)), 200
    except SQLAlchemyError:
        db.session.rollback()
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422


@bp.route('/<string:username>/', methods=['PUT'])
@bp.route('/<string:username>', methods=['PUT'])
@auth.login_required(role='admin')
def update_user(username: str):
    """
    Creates a new user with its random token. Requests parameters can be:
      - valid_until: A string containing the date and time the user validity with
      - timezone
      - token

    :return: A new user object
    :rtype: gisfire_api.user.User
    """

    # Check that all needed parameters are present
    if (request.values is None) or not (1 <= len(request.values) <= 3):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
    if not set(request.values.keys()) <= {'valid_until', 'timezone', 'token'}:
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
    if 'token' in request.values and request.values['token'] != 'new':
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
    if 'timezone' in request.values and 'valid_until' not in request.values:
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422

    # Create the local variables for the user and convert them to proper types
    try:
        user = db.session.execute(select(User).where(User.username == username)).scalar_one()
        if 'valid_until' in request.values:
            valid_until = dateutil.parser.isoparse(request.values['valid_until'])
            if valid_until.tzinfo is None:
                if 'timezone' in request.values:
                    valid_until = pytz.timezone(request.values['timezone']).localize(valid_until)
                    user.tzinfo = str(pytz.timezone(request.values['timezone']))
                else:
                    valid_until = datetime.datetime(year=valid_until.year, month=valid_until.month, day=valid_until.day, hour=valid_until.hour, minute=valid_until.minute, second=valid_until.second, tzinfo=pytz.UTC)
                    user.tzinfo = str(pytz.UTC)
            else:
                if 'timezone' in request.values:
                    raise ValueError("Timezone provided with timezone aware date")
            user.valid_until = valid_until
        if 'token' in request.values:
            new_user = User(username=username)
            user.token = new_user.token
        db.session.commit()
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 200,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(dict(user)), 200
    except (SQLAlchemyError, ValueError, UnknownTimeZoneError):
        db.session.rollback()
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422


@bp.route('/<string:username>/', methods=['DELETE'])
@bp.route('/<string:username>', methods=['DELETE'])
@auth.login_required(role='admin')
def delete_user(username: str):
    """
    Deletes an existing user

    :return: A new user object
    :rtype: gisfire_api.user.User
    """
    # Check that all needed parameters are present
    if (request.values is not None) and (len(request.values) > 0):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422

    # Try to get the existing user
    try:
        user = db.session.execute(select(User).where(User.username == username)).scalar_one()
        db.session.delete(user)
        db.session.commit()
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 200,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify({}), 200
    except SQLAlchemyError:
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
