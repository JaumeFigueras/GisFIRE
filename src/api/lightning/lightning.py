#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import dateutil.parser

from flask import Blueprint
from flask import jsonify
from flask import request
from flask import Response

from src.api import auth
from src.api import db
from src.api import error_response
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
    # Check Data providers
    args = dict()
    data_provider: str = request.args.get("data_provider")
    if data_provider is None:
        return error_response(request, auth, 400, "No data_provider provided")
    elif data_provider not in ['Meteo.cat', ]:
        return error_response(request, auth, 404, "No valid data_provider provided")
    # Check from date
    from_date: Union[str, datetime.datetime, None] = request.args.get("from")
    if from_date is not None:
        try:
            from_date = dateutil.parser.isoparse(from_date)
            args['from_date'] = from_date
        except ValueError:
            return error_response(request, auth, 404, "No valid from date provided")
    # Check to date
    to_date: Union[str, datetime.datetime, None] = request.args.get("to")
    if to_date is not None:
        try:
            to_date = datetime.datetime.strptime(to_date, '%Y-%m-%dT%H:%M:%S%z')
            args['to_date'] = to_date
        except ValueError:
            return error_response(request, auth, 404, "No valid to date provided")
    # Check order_by and its parameters
    order_by: Union[str, None] = request.args.get("order_by")
    order: List[Tuple[str, str]] = list()
    if order_by is not None and len(order_by.split(',')) > 2:
        return error_response(request, auth, 404, "No valid number of order by parameter elements")
    if order_by is not None:
        for item in order_by.split(','):
            if len(item.split(':')) == 1:
                elem = item
                sort = 'asc'
            elif len(item.split(':')) == 2:
                elem = item.split(':')[0]
                sort = item.split(':')[1]
                if sort not in ['asc', 'desc']:
                    return error_response(request, auth, 404, "No valid order by sort parameter")
            else:
                return error_response(request, auth, 404, "No valid order by parameter")
            if elem not in ['date', 'radius']:
                return error_response(request, auth, 404, "No valid order by parameter")
            if elem in [item for item, _ in order]:
                return error_response(request, auth, 404, "Repeated order by parameter")
            order.append((elem, sort))
        args['order'] = order
    epsg: Union[str, int, None] = request.args.get("epsg")
    if epsg is not None:
        try:
            epsg = int(epsg)
        except ValueError:
            return error_response(request, auth, 404, "No valid epsg parameter")
    x: Union[str, float, None] = request.args.get("x")
    if x is not None:
        try:
            x = float(x)
        except ValueError:
            return error_response(request, auth, 404, "No valid x parameter")
    y: Union[str, float, None] = request.args.get("y")
    if y is not None:
        try:
            y = float(y)
        except ValueError:
            return error_response(request, auth, 404, "No valid y parameter")
    radius: Union[str, float, None] = request.args.get("radius")
    if radius is not None:
        try:
            radius = float(radius)
        except ValueError:
            return error_response(request, auth, 404, "No valid radius parameter")
    if ((x is not None) or (y is not None) or (radius is not None)) and not (x is not None and y is not None and epsg is not None and radius is not None):
        return error_response(request, auth, 404, "No valid location parameters")
    else:
        args['epsg'] = epsg
        args['x'] = x
        args['y'] = y
        args['radius'] = radius
    limit: Union[str, int, None] = request.args.get("limit")
    if limit is not None:
        try:
            limit = int(limit)
            args['limit'] = limit
        except ValueError:
            return error_response(request, auth, 404, "No valid limit parameter")
    offset: Union[str, int, None] = request.args.get("offset")
    if offset is not None:
        try:
            offset = int(offset)
            args['offset'] = offset
        except ValueError:
            return error_response(request, auth, 404, "No valid offset parameter")
    if offset is not None and len(order) == 0:
        return error_response(request, auth, 404, "No order argument while offset parameter present")

    lightnings: List[MeteocatLightning] = list()
    if data_provider == 'Meteo.cat':
        lightnings = get_meteocat_lightning(**args)
    user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values),
                             200, auth.current_user())
    db.session.add(user_access)
    db.session.commit()
    return jsonify([dict(lightning) for lightning in lightnings]), 200
