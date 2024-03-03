# -*- coding: utf-8 -*-
from __future__ import annotations

import time

import pytest

from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.base import BackgroundJobWithDodging
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.config import config
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.types import MQTTMessage
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_unit_name


def pause() -> None:
    # to avoid race conditions
    time.sleep(0.5)


def test_states() -> None:
    unit = get_unit_name()
    exp = "test_states"

    bj = BackgroundJob(unit=unit, experiment=exp)
    pause()
    assert bj.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/background_job/$state/set", "sleeping")
    pause()
    assert bj.state == "sleeping"

    publish(f"pioreactor/{unit}/{exp}/background_job/$state/set", "ready")
    pause()
    assert bj.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/background_job/$state/set", "init")
    pause()
    assert bj.state == "init"

    # it's kinda an antipattern to use this disconnect method from the main
    # thread. Better, if in the main thread and able to, to call bj.clean_up().
    # There's no 100% guarantee that this cleans up properly since it is called
    # in the sub thread, which means it's cleaning itself up?? Not clear!
    publish(f"pioreactor/{unit}/{exp}/background_job/$state/set", "disconnected")
    pause()
    assert bj.state == bj.DISCONNECTED
    bj.clean_up()


def test_init_state_is_sent_to_mqtt() -> None:
    # regression test
    exp = "test_init_state_is_sent_to_mqtt"
    unit = get_unit_name()
    states = []

    def update_state(msg: MQTTMessage) -> None:
        states.append(msg.payload.decode())

    subscribe_and_callback(
        update_state, f"pioreactor/{unit}/{exp}/background_job/$state", allow_retained=False
    )

    with BackgroundJob(unit=unit, experiment=exp):
        pause()
        pause()

    assert len(states) == 3
    assert states == ["init", "ready", "disconnected"]


def test_jobs_connecting_and_disconnecting_will_still_log_to_mqtt() -> None:
    # see note in base.py about create_logger
    unit = get_unit_name()
    exp = "test_jobs_connecting_and_disconnecting_will_still_log_to_mqtt"

    with collect_all_logs_of_level("WARNING", unit, exp) as bucket:
        with BackgroundJob(unit=unit, experiment=exp) as bj:
            pause()
            pause()
            pause()
            bj.logger.warning("test1")
            pause()
            pause()
            pause()

        with BackgroundJob(unit=unit, experiment=exp) as bj:
            pause()
            pause()
            bj.logger.warning("test2")
            pause()
            pause()

    assert len(bucket) == 2


def test_error_in_subscribe_and_callback_is_logged() -> None:
    class TestJob(BackgroundJob):
        job_name = "test_job"

        def __init__(self, *args, **kwargs) -> None:
            super(TestJob, self).__init__(*args, **kwargs)
            self.start_passive_listeners()

        def start_passive_listeners(self) -> None:
            self.subscribe_and_callback(self.callback, "pioreactor/testing/subscription")

        def callback(self, msg: MQTTMessage) -> None:
            print(1 / 0)

    experiment = "test_error_in_subscribe_and_callback_is_logged"

    with collect_all_logs_of_level("ERROR", get_unit_name(), experiment) as error_logs:
        with TestJob(unit=get_unit_name(), experiment=experiment):
            pause()
            pause()
            publish("pioreactor/testing/subscription", "test", retain=False)
            pause()
            pause()
            pause()

    assert len(error_logs) > 0
    assert "division by zero" in error_logs[0]["message"]


def test_what_happens_when_an_error_occurs_in_init_but_we_catch_and_disconnect() -> None:
    class TestJob(BackgroundJob):
        job_name = "testjob"

        def __init__(self, unit: str, experiment: str) -> None:
            super(TestJob, self).__init__(unit=unit, experiment=experiment)
            try:
                raise ZeroDivisionError()
            except Exception as e:
                self.logger.error("Error!")
                self.clean_up()
                raise e

    exp = "test_what_happens_when_an_error_occurs_in_init_but_we_catch_and_disconnect"
    publish(f"pioreactor/unit/{exp}/testjob/$state", None, retain=True)
    state = []

    def update_state(msg: MQTTMessage) -> None:
        state.append(msg.payload.decode())

    subscribe_and_callback(update_state, f"pioreactor/unit/{exp}/testjob/$state")

    with pytest.raises(ZeroDivisionError):
        with TestJob(unit="unit", experiment=exp):
            pass

    pause()
    assert state[-1] == "disconnected"

    with local_intermittent_storage("job_metadata_testjob") as cache:
        assert cache["is_running"] == "0"


def test_state_transition_callbacks() -> None:
    class TestJob(BackgroundJob):
        job_name = "testjob"
        called_on_init = False
        called_on_ready = False
        called_on_sleeping = False
        called_on_ready_to_sleeping = False
        called_on_sleeping_to_ready = False
        called_on_init_to_ready = False

        def __init__(self, unit: str, experiment: str) -> None:
            super(TestJob, self).__init__(unit=unit, experiment=experiment)

        def on_init(self) -> None:
            self.called_on_init = True

        def on_ready(self) -> None:
            self.called_on_ready = True

        def on_sleeping(self) -> None:
            self.called_on_sleeping = True

        def on_ready_to_sleeping(self) -> None:
            self.called_on_ready_to_sleeping = True

        def on_sleeping_to_ready(self) -> None:
            self.called_on_sleeping_to_ready = True

        def on_init_to_ready(self) -> None:
            self.called_on_init_to_ready = True

    unit, exp = get_unit_name(), "test_state_transition_callbacks"
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
        job_name = "testjob"
        published_settings = {
            "some_key": {
                "datatype": "float",
                "units": "%",  # type: ignore
                "settable": True,
            },  # units is wrong, should be unit.
        }

        def __init__(self, *args, **kwargs) -> None:
            super(TestJob, self).__init__(*args, **kwargs)

    exp = "test_bad_key_in_published_settings"
    with pytest.raises(ValueError):
        with TestJob(unit=get_unit_name(), experiment=exp):
            pass


def test_bad_setting_name_in_published_settings() -> None:
    class TestJob(BackgroundJob):
        job_name = "job"
        published_settings = {
            "some--!4key": {
                "datatype": "float",
                "settable": True,
            },
        }

        def __init__(self, *args, **kwargs) -> None:
            super(TestJob, self).__init__(*args, **kwargs)

    exp = "test_bad_setting_name_in_published_settings"
    with pytest.raises(ValueError):
        with TestJob(unit=get_unit_name(), experiment=exp):
            pass


def test_editing_readonly_attr_via_mqtt() -> None:
    class TestJob(BackgroundJob):
        job_name = "job"
        published_settings = {
            "readonly_attr": {
                "datatype": "float",
                "settable": False,
            },
        }

    exp = "test_editing_readonly_attr_via_mqtt"

    with collect_all_logs_of_level("WARNING", get_unit_name(), exp) as logs:
        with TestJob(unit=get_unit_name(), experiment=exp):
            publish(
                f"pioreactor/{get_unit_name()}/{exp}/job/readonly_attr/set",
                1.0,
            )
            pause()
            pause()
            pause()

    assert len(logs) > 0
    assert any(["readonly" in log["message"] for log in logs])


def test_persist_in_published_settings() -> None:
    class TestJob(BackgroundJob):
        job_name = "test_job"
        published_settings = {
            "persist_this": {"datatype": "float", "settable": True, "persist": True},
            "dont_persist_this": {
                "datatype": "float",
                "settable": True,
            },
        }

        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.persist_this = "persist_this"
            self.dont_persist_this = "dont_persist_this"

    exp = "test_persist_in_published_settings"

    with TestJob(unit=get_unit_name(), experiment=exp):
        pause()
        pause()

    pause()
    msg = subscribe(
        f"pioreactor/{get_unit_name()}/{exp}/test_job/persist_this",
        timeout=2,
    )
    assert msg is not None
    assert msg.payload.decode() == "persist_this"

    msg = subscribe(
        f"pioreactor/{get_unit_name()}/{exp}/test_job/dont_persist_this",
        timeout=2,
    )
    assert msg is None


def test_sys_exit_does_exit() -> None:
    class AllIDoIsExit:
        def exit(self):
            import sys

            sys.exit()

    class TestJob(BackgroundJob):
        job_name = "job"

        def __init__(self, *args, **kwargs) -> None:
            super(TestJob, self).__init__(*args, **kwargs)
            self.all_i_do_is_exit = AllIDoIsExit()

        def call_all_i_do_is_exit(self):
            self.all_i_do_is_exit.exit()

    with pytest.raises(SystemExit):
        with TestJob(unit=get_unit_name(), experiment="test_sys_exit_does_exit") as t:
            t.call_all_i_do_is_exit()


def test_adding_key_in_published_settings() -> None:
    exp = "test_adding_key_in_published_settings"

    class TestJob(BackgroundJob):
        job_name = "test_job"

        def __init__(self, *args, **kwargs) -> None:
            super(TestJob, self).__init__(*args, **kwargs)
            self.add_to_published_settings("test", {"datatype": "string", "persist": True, "settable": True})

    with TestJob(unit=get_unit_name(), experiment=exp):
        msg = subscribe(f"pioreactor/testing_unit/{exp}/test_job/test/$settable")
        assert msg is not None
        assert msg.payload.decode() == "True"
        msg = subscribe(f"pioreactor/testing_unit/{exp}/test_job/$properties")
        assert msg is not None
        assert msg.payload.decode() == "state,test"


def test_cleans_up_mqtt() -> None:
    class TestJob(BackgroundJob):
        job_name = "job"
        published_settings = {
            "readonly_attr": {
                "datatype": "float",
                "settable": False,
            },
        }

    exp = "test_cleans_up_mqtt"

    with TestJob(unit=get_unit_name(), experiment=exp):
        msg = subscribe(f"pioreactor/+/{exp}/job/readonly_attr/#", timeout=0.5)
        assert msg is not None

        msg = subscribe(f"pioreactor/+/{exp}/job/$properties", timeout=0.5)
        assert msg is not None

        msg = subscribe(f"pioreactor/+/{exp}/job/$state", timeout=0.5)
        assert msg is not None

        pause()

    msg = subscribe(f"pioreactor/+/{exp}/job/readonly_attr/#", timeout=0.5)
    assert msg is None

    msg = subscribe(f"pioreactor/+/{exp}/job/$properties", timeout=0.5)
    assert msg is None

    msg = subscribe(f"pioreactor/+/{exp}/job/$state", timeout=0.5)
    assert msg is not None


def test_dodging() -> None:
    config["just_pause"] = {}
    config["just_pause"]["post_delay_duration"] = "0.75"
    config["just_pause"]["pre_delay_duration"] = "0.25"
    config["just_pause"]["enable_dodging_od"] = "1"

    def post_cb(od_job, batched_readings, *args):
        od_job.logger.notice(f"Done OD Reading at {time.time()}")

    def pre_cb(od_job, *args):
        od_job.logger.notice(f"Start OD Reading at {time.time()}")

    ODReader.add_pre_read_callback(pre_cb)
    ODReader.add_post_read_callback(post_cb)

    class JustPause(BackgroundJobWithDodging):
        job_name = "just_pause"

        def __init__(self):
            super().__init__(unit=get_unit_name(), experiment="test_dodging")

        def action_to_do_before_od_reading(self):
            self.logger.notice(f"   Pausing at {time.time()} 🛑")

        def action_to_do_after_od_reading(self):
            self.logger.notice(f"   Unpausing at {time.time()} 🟢")

    st = start_od_reading(
        "90",
        None,
        unit=get_unit_name(),
        experiment="test_dodging",
        fake_data=True,
        use_calibration=False,
    )
    time.sleep(5)

    with collect_all_logs_of_level("NOTICE", unit=get_unit_name(), experiment="test_dodging") as bucket:
        with JustPause():
            time.sleep(26)
            assert len(bucket) > 4, bucket

    st.clean_up()
    ODReader._post_read.clear()


def test_dodging_when_od_reading_stops_first() -> None:
    config["just_pause"] = {}
    config["just_pause"]["post_delay_duration"] = "0.75"
    config["just_pause"]["pre_delay_duration"] = "0.25"
    config["just_pause"]["enable_dodging_od"] = "1"

    class JustPause(BackgroundJobWithDodging):
        job_name = "just_pause"

        def __init__(self):
            super().__init__(unit=get_unit_name(), experiment="test_dodging_when_od_reading_stops_first")

        def action_to_do_before_od_reading(self):
            self.logger.notice(f"   Pausing at {time.time()} 🛑")

        def action_to_do_after_od_reading(self):
            self.logger.notice(f"   Unpausing at {time.time()} 🟢")

    st = start_od_reading(
        "90",
        None,
        unit=get_unit_name(),
        experiment="test_dodging_when_od_reading_stops_first",
        fake_data=True,
        use_calibration=False,
    )
    time.sleep(5)

    with collect_all_logs_of_level(
        "ERROR", unit=get_unit_name(), experiment="test_dodging_when_od_reading_stops_first"
    ) as bucket:
        with JustPause():
            time.sleep(5)
            st.clean_up()
            time.sleep(5)

        assert len(bucket) == 0


def test_disabled_dodging() -> None:
    exp = "test_disabled_dodging"
    config["just_pause"] = {}
    config["just_pause"]["post_delay_duration"] = "0.2"
    config["just_pause"]["pre_delay_duration"] = "0.1"
    config["just_pause"]["enable_dodging_od"] = "1"

    class JustPause(BackgroundJobWithDodging):
        job_name = "just_pause"
        published_settings = {"test": {"datatype": "float", "settable": True}}

        def __init__(self):
            super().__init__(unit=get_unit_name(), experiment=exp)

        def action_to_do_before_od_reading(self):
            self.logger.notice("Pausing")

        def action_to_do_after_od_reading(self):
            self.logger.notice("Unpausing")

    with collect_all_logs_of_level("NOTICE", unit=get_unit_name(), experiment=exp) as bucket:
        jp = JustPause()
        assert set(jp.published_settings.keys()) == set(["test", "state", "enable_dodging_od"])

        od = start_od_reading(
            "90",
            None,
            interval=5,  # needed
            unit=get_unit_name(),
            experiment=exp,
            fake_data=True,
            use_calibration=False,
        )
        time.sleep(5)
        jp.set_enable_dodging_od(False)
        time.sleep(20)
        assert len(bucket) == 2

        jp.set_enable_dodging_od(True)
        time.sleep(12)
        assert len(bucket) == 4

    od.clean_up()
    jp.clean_up()


def test_job_write_metadata_correctly() -> None:
    experiment = "test_job_write_metadata_correctly"
    unit = get_unit_name()

    with BackgroundJob(unit=unit, experiment=experiment) as bj:
        with local_intermittent_storage(f"job_metadata_{bj.job_name}") as cache:
            assert cache["unit"] == unit
            assert cache["experiment"] == experiment
            assert cache["source"] == "app"
            assert cache["is_running"] == "1"
            assert cache["ended_at"] == ""

    with local_intermittent_storage(f"job_metadata_{bj.job_name}") as cache:
        assert cache["is_running"] == "0"
        assert cache["ended_at"] != ""


def test_that_job_will_republish_state_if_not_correct_in_broker() -> None:
    experiment = "test_that_job_will_republish_state_if_not_correct_in_broker"
    unit = get_unit_name()

    with BackgroundJob(unit=unit, experiment=experiment) as bj:
        pause()
        assert bj.state == bj.READY
        assert subscribe(f"pioreactor/{unit}/{experiment}/{bj.job_name}/$state").payload.decode() == bj.READY  # type: ignore
        pause()
        # override state
        publish(f"pioreactor/{unit}/{experiment}/{bj.job_name}/$state", "lost", retain=True)
        pause()
        assert bj.state == bj.READY
        assert subscribe(f"pioreactor/{unit}/{experiment}/{bj.job_name}/$state").payload.decode() == bj.READY  # type: ignore
