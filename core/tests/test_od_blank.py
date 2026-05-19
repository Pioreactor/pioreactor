# -*- coding: utf-8 -*-
import json
from types import TracebackType

import pytest
from pioreactor import structs
from pioreactor import whoami
from pioreactor.actions.od_blank import od_blank
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_datetime


@pytest.mark.slow
def test_returns_means_and_outputs_to_cache() -> None:
    experiment = "test_returns_means_and_outputs_to_cache"
    with temporary_config_change(config, "od_config.photodiode_channel", "1", "90"):
        output = od_blank(n_samples=10, experiment=experiment)
    assert "1" in output

    with local_persistent_storage("od_blank") as cache:
        assert json.loads(cache[experiment])["1"] == output["1"]


def test_clears_temporary_ir_led_reference_normalization_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    import pioreactor.background_jobs.od_reading as od_reading_module

    experiment = "test_clears_temporary_ir_led_reference_normalization_cache"
    testing_experiment = whoami.get_testing_experiment_name()

    with local_persistent_storage("ir_led_reference_normalization") as cache:
        cache[testing_experiment] = "999.0"

    class FakeODStream:
        def __init__(self) -> None:
            self._count = 0

        def __enter__(self) -> "FakeODStream":
            with local_persistent_storage("ir_led_reference_normalization") as cache:
                assert testing_experiment not in cache
                cache[testing_experiment] = "0.123"
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            return None

        def __iter__(self) -> "FakeODStream":
            return self

        def __next__(self) -> structs.ODReadings:
            if self._count >= 7:
                raise StopIteration

            self._count += 1
            timestamp = current_utc_datetime()
            return structs.ODReadings(
                timestamp=timestamp,
                ods={
                    "2": structs.RawODReading(
                        timestamp=timestamp,
                        angle="90",
                        od=0.2,
                        channel="2",
                        ir_led_intensity=80.0,
                    )
                },
            )

    def fake_start_od_reading(*args: object, **kwargs: object) -> FakeODStream:
        assert kwargs["experiment"] == testing_experiment
        return FakeODStream()

    monkeypatch.setattr(od_reading_module, "start_od_reading", fake_start_od_reading)

    output = od_blank(n_samples=7, experiment=experiment)

    assert output == {"2": 0.2}
    with local_persistent_storage("ir_led_reference_normalization") as cache:
        assert testing_experiment not in cache
