# -*- coding: utf-8 -*-
import json

import pytest
from pioreactor.actions.od_blank import od_blank
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.utils import local_persistent_storage


@pytest.mark.slow
def test_returns_means_and_outputs_to_cache() -> None:
    experiment = "test_returns_means_and_outputs_to_cache"
    with temporary_config_change(config, "od_config.photodiode_channel", "1", "90"):
        output = od_blank(n_samples=10, experiment=experiment)
    assert "1" in output

    with local_persistent_storage("od_blank") as cache:
        assert json.loads(cache[experiment])["1"] == output["1"]
