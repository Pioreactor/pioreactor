# -*- coding: utf-8 -*-
import time
import pytest
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.leader.watchdog import WatchDog
from pioreactor.background_jobs.monitor import Monitor
from pioreactor.whoami import (
    get_unit_name,
    get_latest_experiment_name,
    UNIVERSAL_EXPERIMENT,
)
from pioreactor.pubsub import publish, subscribe_and_callback
from pioreactor.config import leader_hostname
from pioreactor.utils import local_intermittent_storage


def pause() -> None:
    # to avoid race conditions
    time.sleep(0.5)


def test_states() -> None:
    unit = get_unit_name()
    exp = get_latest_experiment_name()

    bj = BackgroundJob(job_name="job", unit=unit, experiment=exp)
    pause()
    assert bj.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "sleeping")
    pause()
    assert bj.state == "sleeping"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "ready")
    pause()
    assert bj.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "init")
    pause()
    assert bj.state == "init"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "disconnected")
    pause()
    bj.set_state(bj.DISCONNECTED)


@pytest.mark.skip(reason="hangs")
def test_watchdog_will_try_to_fix_lost_job() -> None:
    wd = WatchDog(leader_hostname, UNIVERSAL_EXPERIMENT)
    pause()

    # start a monitor job
    monitor = Monitor(leader_hostname, UNIVERSAL_EXPERIMENT)
    pause()
    pause()

    # suppose it disconnects from broker for long enough that the last will is sent
    publish(f"pioreactor/{leader_hostname}/{UNIVERSAL_EXPERIMENT}/monitor/$state", "lost")

    pause()
    pause()
    pause()
    pause()
    pause()
    pause()
    pause()
    assert monitor.sub_client._will

    wd.set_state(wd.DISCONNECTED)
    monitor.set_state(monitor.DISCONNECTED)


def test_jobs_connecting_and_disconnecting_will_still_log_to_mqtt() -> None:
    # see note in base.py about create_logger

    unit: str = get_unit_name()
    exp: str = get_latest_experiment_name()

    results = []

    def cb(msg):
        if "WARNING" in msg.payload.decode():
            results.append([msg.payload])

    subscribe_and_callback(cb, f"pioreactor/{unit}/{exp}/logs/app")

    bj = BackgroundJob(job_name="job", unit=unit, experiment=exp)
    bj.logger.warning("test1")

    # disonnect, which should clear logger handlers (but may not...)
    bj.set_state(bj.DISCONNECTED)

    bj = BackgroundJob(job_name="job", unit=unit, experiment=exp)
    bj.logger.warning("test2")

    pause()
    pause()
    assert len(results) == 2
    bj.set_state(bj.DISCONNECTED)


def test_error_in_subscribe_and_callback_is_logged() -> None:
    class TestJob(BackgroundJob):
        def __init__(self, *args, **kwargs):
            super(TestJob, self).__init__(*args, **kwargs)
            self.start_passive_listeners()

        def start_passive_listeners(self):
            self.subscribe_and_callback(self.callback, "pioreactor/testing/subscription")

        def callback(self, msg):
            print(1 / 0)

    error_logs = []

    def collect_error_logs(msg):
        if "ERROR" in msg.payload.decode():
            error_logs.append(msg)

    subscribe_and_callback(
        collect_error_logs,
        f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/logs/app",
    )

    with TestJob(
        job_name="job", unit=get_unit_name(), experiment=get_latest_experiment_name()
    ):
        publish("pioreactor/testing/subscription", "test")
        pause()
        pause()
        assert len(error_logs) > 0
        assert "division by zero" in error_logs[0].payload.decode()


@pytest.mark.xfail
def test_what_happens_when_an_error_occurs_in_init_with_no_catch() -> None:
    class TestJob(BackgroundJob):
        def __init__(self, unit, experiment):
            super(TestJob, self).__init__(
                job_name="testjob", unit=unit, experiment=experiment
            )
            1 / 0  # we should try to catch this, and do a disconnect as well

    state = []
    publish("pioreactor/unit/exp/testjob/$state", None, retain=True)

    def update_state(msg):
        state.append(msg.payload.decode())

    subscribe_and_callback(update_state, "pioreactor/unit/exp/testjob/$state")

    with pytest.raises(ZeroDivisionError):
        with TestJob(unit="unit", experiment="exp"):
            pass

    time.sleep(0.25)
    assert state[-1] == "lost"


def test_what_happens_when_an_error_occurs_in_init_but_we_catch_and_disconnect() -> None:
    class TestJob(BackgroundJob):
        def __init__(self, unit, experiment):
            super(TestJob, self).__init__(
                job_name="testjob", unit=unit, experiment=experiment
            )
            try:
                1 / 0
            except Exception as e:
                self.logger.error("Error!")
                self.set_state("disconnected")
                raise e

    publish("pioreactor/unit/exp/testjob/$state", None, retain=True)
    state = []

    def update_state(msg):
        state.append(msg.payload.decode())

    subscribe_and_callback(update_state, "pioreactor/unit/exp/testjob/$state")

    with pytest.raises(ZeroDivisionError):
        with TestJob(unit="unit", experiment="exp"):
            pass

    pause()
    assert state[-1] == "disconnected"

    with local_intermittent_storage("pio_jobs_running") as cache:
        assert cache["testjob"] == b"0"  # cleaned up correctly


def test_state_transition_callbacks() -> None:
    class TestJob(BackgroundJob):
        called_on_init = False
        called_on_ready = False
        called_on_sleeping = False
        called_on_ready_to_sleeping = False
        called_on_sleeping_to_ready = False
        called_on_init_to_ready = False

        def __init__(self, unit, experiment):
            super(TestJob, self).__init__(
                job_name="testjob", unit=unit, experiment=experiment
            )

        def on_init(self):
            self.called_on_init = True

        def on_ready(self):
            self.called_on_ready = True

        def on_sleeping(self):
            self.called_on_sleeping = True

        def on_ready_to_sleeping(self):
            self.called_on_ready_to_sleeping = True

        def on_sleeping_to_ready(self):
            self.called_on_sleeping_to_ready = True

        def on_init_to_ready(self):
            self.called_on_init_to_ready = True

    unit, exp = get_unit_name(), get_latest_experiment_name()
    with TestJob(unit, exp) as tj:
        assert tj.called_on_init
        assert tj.called_on_init_to_ready
        assert tj.called_on_ready
        publish(f"pioreactor/{unit}/{exp}/{tj.job_name}/$state/set", tj.SLEEPING)
        pause()
        pause()
        pause()
        pause()
        assert tj.called_on_ready_to_sleeping
        assert tj.called_on_sleeping

        publish(f"pioreactor/{unit}/{exp}/{tj.job_name}/$state/set", tj.READY)
        pause()
        pause()
        pause()
        pause()
        assert tj.called_on_sleeping_to_ready


def test_bad_key_in_published_settings() -> None:
    class TestJob(BackgroundJob):

        published_settings = {
            "some_key": {
                "datatype": "float",
                "units": "%",  # type: ignore
                "settable": True,
            },  # units is wrong, should be unit.
        }

        def __init__(self, *args, **kwargs):
            super(TestJob, self).__init__(*args, **kwargs)

    warning_logs = []

    def collect_warning_logs(msg):
        if "WARNING" in msg.payload.decode():
            warning_logs.append(msg)

    subscribe_and_callback(
        collect_warning_logs,
        f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/logs/app",
    )

    with TestJob(
        job_name="job", unit=get_unit_name(), experiment=get_latest_experiment_name()
    ):
        pause()
        pause()
        assert len(warning_logs) > 0
        assert "Found extra property" in warning_logs[0].payload.decode()


def test_bad_setting_name_in_published_settings() -> None:
    class TestJob(BackgroundJob):

        published_settings = {
            "some--!4key": {
                "datatype": "float",
                "settable": True,
            },
        }

        def __init__(self, *args, **kwargs):
            super(TestJob, self).__init__(*args, **kwargs)

    with pytest.raises(ValueError):
        TestJob(
            job_name="job", unit=get_unit_name(), experiment=get_latest_experiment_name()
        )


def test_editing_readonly_attr_via_mqtt() -> None:
    class TestJob(BackgroundJob):

        published_settings = {
            "readonly_attr": {
                "datatype": "float",
                "settable": False,
            },
        }

    warning_logs = []

    def collect_logs(msg):
        if "readonly" in msg.payload.decode():
            warning_logs.append(msg)

    subscribe_and_callback(
        collect_logs,
        f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/logs/app",
    )

    with TestJob(
        job_name="job", unit=get_unit_name(), experiment=get_latest_experiment_name()
    ):
        publish(
            f"pioreactor/{get_unit_name()}/{get_latest_experiment_name()}/job/readonly_attr/set",
            1.0,
        )
        pause()

    assert len(warning_logs) > 0
