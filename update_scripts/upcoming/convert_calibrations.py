# -*- coding: utf-8 -*-
# convert_calibrations.py
from __future__ import annotations

import json

from pioreactor.utils import local_persistant_storage
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def transform_cache(cache):
    for name in list(cache):
        cal = json.loads(cache[name])
        try:
            cal["created_at"] = cal["timestamp"]
            cal["pioreactor_unit"] = unit
            cal.pop("timestamp")
            cache[name] = json.dumps(cal, separators=(",", ":")).encode()
        except Exception as e:
            print(e)


# pump calibrations
with local_persistant_storage("pump_calibrations") as cache:
    transform_cache(cache)

with local_persistant_storage("current_pump_calibration") as cache:
    transform_cache(cache)


# od600 calibrations
with local_persistant_storage("od_calibrations") as cache:
    transform_cache(cache)

with local_persistant_storage("current_od_calibration") as cache:
    transform_cache(cache)
