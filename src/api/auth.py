#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask_httpauth import HTTPBasicAuth
from flask import jsonify
from flask import request
import json

auth = HTTPBasicAuth()


@auth.error_handler
def auth_error(status):
    """

    :param status:
    :return:
    """
    from .user import UserAccess
    from . import db

    UserAccess(request.remote_addr, request.url, request.method, json.dumps(dict(request.values)),
               auth.current_user()).record_access(db, 401)

    return jsonify(status_code=401), 401


@auth.verify_password
def verify_password(username, password):
    """

    :param username:
    :param password:
    :return:
    """
    from .user import User

    user = User.query.filter(User.username == username, User.token == password).first()
    return user


@auth.get_user_roles
def get_user_roles(user):
    """

    :param user:
    :type user: gisfire_api.user.User
    :return:
    """
    if user.is_admin:
        return ['admin', 'user']
    return ['user']