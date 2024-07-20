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


@bp.route('/', methods=['POST'], defaults={'username': None})
@bp.route('', methods=['POST'], defaults={'username': None})
@bp.route('/<string:username>/', methods=['PUT'])
@bp.route('/<string:username>', methods=['PUT'])
@auth.login_required(role='admin')
def manage_user(username: str):
    """
    Creates a new user with its random token. Requests parameters can be:
      - username: A string containing the username of the new user.
      - valid_until: A string containing the date and time the user validity with
      - timezone

    :return: A new user object
    :rtype: gisfire_api.user.User
    """

    # Check that all needed parameters are present
    if (request.values is None) or ('username' not in request.values) or not (1 <= len(request.values) <= 3):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
    if (len(request.values) == 2) and ('valid_until' not in request.values):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422
    if (len(request.values) == 3) and (('valid_until' not in request.values) or ('timezone' not in request.values)):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422

    # Create the local variables for the user and convert them to proper types
    if request.method == 'POST':
        username = request.values['username']
    try:
        if 'valid_until' in request.values:
            valid_until = dateutil.parser.isoparse(request.values['valid_until'])
            if valid_until.tzinfo is None:
                if 'timezone' in request.values:
                    valid_until = valid_until.replace(tzinfo=pytz.timezone(request.values['timezone']))
                else:
                    valid_until = valid_until.replace(tzinfo=pytz.UTC)
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
        if request.method == 'POST':
            user = User(username=username, valid_until=valid_until)
            db.session.add(user)
            db.session.commit()
        else:
            user = db.session.execute(select(User).where(User.username == username)).scalar_one()
            user.valid_until = valid_until
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


@bp.route('/<string:username>/', methods=['DELETE'])
@bp.route('/<string:username>', methods=['DELETE'])
@auth.login_required(role='admin')
def delete_user():
    """
    Deletes an existing user

    :return: A new user object
    :rtype: gisfire_api.user.User
    """
    # Check that all needed parameters are present
    if (request.values is None) or ('username' not in request.values) or (len(request.values) != 1):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 422,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify(status_code=422), 422

    # Create the local variables for the user and convert them to proper types
    username = request.values['username']
    # Try to get the existing user
    user = User.query.filter(User.username == username).first()
    if user is None:
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db, 422)
        return jsonify(status_code=422), 422
    try:
        db.session.delete(user)
        db.session.commit()
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db)
        return jsonify({}), 200
    except exc.SQLAlchemyError:  # pragma: no cover
        # No testing of this code because the database error has to be caused by some malfunction of the system. Testing
        # it changing permissions on-the-fly, and other ways cause collateral side effects. If I can read the user
        # object I can update it unless a broken connection, internet failure, server failure, etc. The record_access
        # function also try to write, so the application doesn't fail
        db.session.rollback()
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db)
        return jsonify(status_code=422), 422