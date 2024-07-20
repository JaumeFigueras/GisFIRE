#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask_httpauth import HTTPBasicAuth
from flask import jsonify
from flask import request
import json

from src.data_model.user import User
from src.data_model.user_access import UserAccess

auth = HTTPBasicAuth()


@auth.error_handler
def auth_error(status):
    """

    :param status:
    :return:
    """
    from src.api import db

    user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 401,
                             auth.current_user())
    db.session.add(user_access)
    db.session.commit()
    return jsonify(status_code=401), 401


@auth.verify_password
def verify_password(username, password):
    """

    :param username:
    :param password:
    :return:
    """
    from src.api import db

    user = db.session.execute(db.select(User).where(User.username == username).where(User.token == password)).scalar_one_or_none()
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
