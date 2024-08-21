#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

from flask import Blueprint
from flask import jsonify
from flask import request
from flask import Response

from src.api import auth
from src.api import db
from src.api import error_response
from src.api.ignition.bomberscat_ignition import get_bomberscat_ignition
from src.data_model.user_access import UserAccess
from src.data_model.wildfire_ignition import WildfireIgnition

from typing import Union
from typing import Tuple
from typing import List

bp = Blueprint("ignition", __name__, url_prefix="/v2/ignition")


@bp.route('/', methods=['GET'])
@bp.route('', methods=['GET'])
@auth.login_required(role='user')
def main() -> Tuple[Response, int]:
    """
    Entry point to get the ignition information

    :return:
    """
    # Check Data providers
    args = dict()
    data_provider: str = request.args.get("data_provider")
    if data_provider is None:
        return error_response(request, auth, 400, "No data_provider provided")
    elif data_provider not in ['Bombers.cat', ]:
        return error_response(request, auth, 404, "No valid data_provider provided")
    # Check from date
    from_date: Union[str, datetime.datetime, None] = request.args.get("from")
    if from_date is not None:
        try:
            from_date = datetime.datetime.strptime(from_date, '%Y-%m-%dT%H:%M:%S%z')
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
    if order_by is not None and ',' in order_by:
        return error_response(request, auth, 404, "No valid number of order by parameter elements")
    if order_by is not None:
        if len(order_by.split(':')) == 2:
            elem = order_by.split(':')[0]
            sort = order_by.split(':')[1]
            if sort not in ['asc', 'desc']:
                return error_response(request, auth, 404, "No valid order by sort parameter")
        else:
            elem = order_by
            sort = 'asc'
        if elem != 'date':
            return error_response(request, auth, 404, "No valid order by parameter")
        order.append((elem, sort))
        args['order'] = order
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

    ignitions: List[WildfireIgnition] = list()
    if data_provider == 'Bombers.cat':
        ignitions = get_bomberscat_ignition(**args)
    user_access = UserAccess(request.remote_addr, request.url, request.method, dict(request.values),
                             200, auth.current_user())
    db.session.add(user_access)
    db.session.commit()
    return jsonify([dict(ignition) for ignition in ignitions]), 200
