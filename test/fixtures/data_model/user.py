#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import datetime

from src.data_model.user import User

from typing import Union
from typing import List


@pytest.fixture(scope='function')
def user_list(request) -> Union[List[User], None]:
    user_1 = User('admin', '1234', True)
    user_2 = User('jack', '5678', False)
    return [user_1, user_2]

