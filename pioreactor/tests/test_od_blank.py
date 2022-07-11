# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from pioreactor.actions.od_blank import od_blank
from pioreactor.config import config
from pioreactor.utils import local_persistant_storage


def test_returns_means_and_outputs_to_cache():
    experiment = "test_returns_means_and_outputs_to_cache"
    config["od_config.photodiode_channel"]["1"] = "90"
    output = od_blank("90", "REF", n_samples=10, experiment=experiment)
    assert "1" in output

    with local_persistant_storage("od_blank") as cache:
        assert json.loads(cache[experiment])["1"] == output["1"]
