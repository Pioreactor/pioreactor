# -*- coding: utf-8 -*-
import time

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


def pause():
    # to avoid race conditions
    time.sleep(0.5)


def test_states():
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


def test_watchdog_will_try_to_fix_lost_job():
    WatchDog(leader_hostname, UNIVERSAL_EXPERIMENT)
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


def test_jobs_connecting_and_disconnecting_will_still_log_to_mqtt():
    # see note in base.py about create_logger

    unit = get_unit_name()
    exp = get_latest_experiment_name()

    results = []

    def cb(msg):
        if "WARNING" in msg.payload.decode():
            results.append([msg.payload])

    subscribe_and_callback(cb, f"pioreactor/{unit}/{exp}/logs/app")

    bj = BackgroundJob(job_name="job", unit=unit, experiment=exp)
    bj.logger.warning("test1")

    # disonnect, which should clear logger handlers (but may not...)
    bj.set_state("disconnected")

    bj = BackgroundJob(job_name="job", unit=unit, experiment=exp)
    bj.logger.warning("test2")

    pause()
    pause()
    assert len(results) == 2


def test_error_in_subscribe_and_callback_is_logged():
    class TestJob(BackgroundJob):
        def __init__(self, *args, **kwargs):
            super(TestJob, self).__init__(*args, **kwargs)
            self.start_passive_listeners()

        def start_passive_listeners(self):
            self.subscribe_and_callback(self.callback, "test/test")

        def callback(self, msg):
            print(1 / 0)

    error_logs = []

    def collect_error_logs(msg):
        if "ERROR" in msg.payload.decode():
            error_logs.append(msg)

    subscribe_and_callback(
        collect_error_logs, "pioreactor/testing_unit/testing_experiment/logs/app"
    )

    TestJob(job_name="job", unit=get_unit_name(), experiment=get_latest_experiment_name())
    publish("test/test", "test")
    pause()
    pause()
    assert len(error_logs) > 0
    assert "division by zero" in error_logs[0].payload.decode()
