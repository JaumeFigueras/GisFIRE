#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytz
import datetime

from flask import Blueprint
from flask import jsonify
from flask import request
from flask import Response
from flask import current_app as app

from src.api import auth
from src.api import db
from src.api.lightning.meteocat_lightning import get_meteocat_lightning
from src.data_model.user_access import UserAccess
from src.meteocat.data_model import MeteocatLightning

from typing import Union
from typing import Tuple
from typing import List

bp = Blueprint("lightning", __name__, url_prefix="/v2/lightning")


@bp.route('/', methods=['GET'])
@bp.route('', methods=['GET'])
@auth.login_required(role='user')
def main() -> Tuple[Response, int]:
    """
    Entry point to get the lightning information

    :return:
    """
    data_provider: str = request.args.get("data_provider")
    if data_provider is None:
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 400,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify({"error": "No data_provider provided", "status_code": 400}), 400
    elif data_provider not in ['Meteo.cat', ]:
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify({"error": "No valid data_provider provided", "status_code": 404}), 404
    from_date: Union[str, datetime.datetime, None] = request.args.get("from")
    if from_date is not None:
        try:
            from_date = datetime.datetime.strptime(from_date, '%Y-%m-%dT%H:%M:%S%z')
        except ValueError:
            user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                     auth.current_user())
            db.session.add(user_access)
            db.session.commit()
            return jsonify({"error": "No valid from date provided", "status_code": 404}), 404
    to_date: Union[str, datetime.datetime, None] = request.args.get("to")
    if to_date is not None:
        try:
            to_date = datetime.datetime.strptime(to_date, '%Y-%m-%dT%H:%M:%S%z')
        except ValueError:
            user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                     auth.current_user())
            db.session.add(user_access)
            db.session.commit()
            return jsonify({"error": "No valid to date provided", "status_code": 404}), 404
    order_by: str = request.args.get("order_by")
    order: List[Tuple[str, str]] = list()
    for item in order_by.split(','):
        if len(item.split(':')) == 1:
            elem = item
            sort = 'asc'
        elif len(item.split(':')) == 2:
            elem = item.split(':')[0]
            sort = item.split(':')[1]
            if sort not in ['asc', 'desc']:
                user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                         auth.current_user())
                db.session.add(user_access)
                db.session.commit()
                return jsonify({"error": "No valid order by sort parameter", "status_code": 404}), 404
        else:
            user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                     auth.current_user())
            db.session.add(user_access)
            db.session.commit()
            return jsonify({"error": "No valid order by parameter", "status_code": 404}), 404
        if elem not in ['date', 'radius']:
            user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                     auth.current_user())
            db.session.add(user_access)
            db.session.commit()
            return jsonify({"error": "No valid order by parameter", "status_code": 404}), 404
        order.append((elem, sort))
    epsg: Union[str, int, None] = request.args.get("epsg")
    if epsg is not None:
        try:
            epsg = int(epsg)
        except ValueError:
            user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                     auth.current_user())
            db.session.add(user_access)
            db.session.commit()
            return jsonify({"error": "No valid epsg parameter", "status_code": 404}), 404
    else:
        if data_provider == 'Meteo.cat':
            epsg = 4258
    x: Union[str, float, None] = request.args.get("x")
    if x is not None:
        try:
            x = float(x)
        except ValueError:
            user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                     auth.current_user())
            db.session.add(user_access)
            db.session.commit()
            return jsonify({"error": "No valid x parameter", "status_code": 404}), 404
    y: Union[str, float, None] = request.args.get("y")
    if y is not None:
        try:
            y = float(y)
        except ValueError:
            user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                     auth.current_user())
            db.session.add(user_access)
            db.session.commit()
            return jsonify({"error": "No valid y parameter", "status_code": 404}), 404
    if ((x is not None) or (y is not None)) and not (x is not None and y is not None and epsg is not None):
        user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                 auth.current_user())
        db.session.add(user_access)
        db.session.commit()
        return jsonify({"error": "No valid location parameters", "status_code": 404}), 404
    radius: Union[str, float, None] = request.args.get("radius")
    if radius is not None:
        try:
            radius = float(radius)
        except ValueError:
            user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values), 404,
                                     auth.current_user())
            db.session.add(user_access)
            db.session.commit()
            return jsonify({"error": "No valid radius parameter", "status_code": 404}), 404
    lightnings: List[MeteocatLightning] = list()
    if data_provider == 'Meteo.cat':
        lightnings = get_meteocat_lightning(from_date=from_date, to_date=to_date, x=x, y=y, epsg=epsg, radius=radius, order=order)
    return jsonify(lightnings), 200
