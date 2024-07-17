from flask import Blueprint
from flask import jsonify
from flask import request
from flask import current_app as app
import datetime
from ..auth import auth
from .. import db
from . import User
from . import UserAccess
from sqlalchemy import exc
import json

bp = Blueprint("auth", __name__, url_prefix="/v1/auth")


@bp.route('/')
@bp.route('')
def main():
    """
    TODO:

    :return:
    """
    UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
               auth.current_user()).record_access(db, 500)
    return jsonify(status_code=500), 500


@bp.route('/token/', methods=['POST'])
@bp.route('/token', methods=['POST'])
@auth.login_required(role='admin')
def create_user():
    """
    Creates a new user with its random token

    :return: A new user object
    :rtype: gisfire_api.user.User
    """

    # Check that all needed parameters are present
    if (request.values is None) or ('username' not in request.values) or ('valid_until' not in request.values) or \
            (len(request.values) != 2):
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db, 422)
        return jsonify(status_code=422), 422

    # Create the local variables for the user and convert them to proper types
    username = request.values['username']
    try:
        valid_until = datetime.datetime.strptime(request.values['valid_until'], '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db, 422)
        return jsonify(status_code=422), 422

    # Try to insert into the database the new user
    user = User(username, valid_until)
    try:
        db.session.add(user)
        db.session.commit()
        app.json_encoder = User.UserJSONEncoder
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db)
        return jsonify(user), 200
    except exc.SQLAlchemyError:
        db.session.rollback()
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)))\
            .record_access(db, 422)
        return jsonify(status_code=422), 422


@bp.route('/token/', methods=['PUT'])
@bp.route('/token', methods=['PUT'])
@auth.login_required(role='admin')
def update_user():
    """
    Updates an existing user. Only the validity date can be updated.

    :return: A new user object
    :rtype: gisfire_api.user.User
    """
    # Check that all needed parameters are present
    if (request.values is None) or ('username' not in request.values) or ('valid_until' not in request.values) or \
            (len(request.values) != 2):
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db, 422)
        return jsonify(status_code=422), 422

    # Create the local variables for the user and convert them to proper types
    username = request.values['username']
    try:
        valid_until = datetime.datetime.strptime(request.values['valid_until'], '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db, 422)
        return jsonify(status_code=422), 422

    # Try to get the existing user
    user = User.query.filter(User.username == username).first()
    if user is None:
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db, 422)
        return jsonify(status_code=422), 422
    user.valid_until = valid_until
    try:
        db.session.commit()
        app.json_encoder = User.UserJSONEncoder
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db)
        return jsonify(user), 200
    except exc.SQLAlchemyError:  # pragma: no cover
        # No testing of this code because the database error has to be caused by some malfunction of the system. Testing
        # it changing permissions on-the-fly, and other ways cause collateral side effects. If I can read the user
        # object I can update it unless a broken connection, internet failure, server failure, etc. The record_access
        # function also try to write, so the application doesn't fail
        db.session.rollback()
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db)
        return jsonify(status_code=422), 422


@bp.route('/token/', methods=['DELETE'])
@bp.route('/token', methods=['DELETE'])
@auth.login_required(role='admin')
def delete_user():
    """
    Deletes an existing user

    :return: A new user object
    :rtype: gisfire_api.user.User
    """
    # Check that all needed parameters are present
    if (request.values is None) or ('username' not in request.values) or (len(request.values) != 1):
        UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
                   auth.current_user()).record_access(db, 422)
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