#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from requests import HTTPError

from typing import Optional


class StatusCodeError(HTTPError):
    def __init__(self, status_code: int, message: Optional[str]):
        super().__init__(status_code, message)
        self.request_status_code = status_code
