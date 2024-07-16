#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json


class NoNoneInList(json.JSONDecoder):
    """
    Simple JSONDecoder class that removes the None elements that appear in the uppermost list. This behaviour is useful
    to discard voided or retires elements that can not be filtered out in the OpenMRS REST API calls
    """
    def decode(self, *args, **kwrds):
        """
        Decode a JSON string using the default JSONDecoder behaviour and when finished removes the None elements in
        the final list
        """
        obj = super().decode(*args, **kwrds)
        if isinstance(obj, list):
            return [i for i in obj if i is not None]
        return obj  # pragma: no cover
