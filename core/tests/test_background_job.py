# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from contextlib import contextmanager

import pytest
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.base import BackgroundJobContrib
from pioreactor.background_jobs.base import BackgroundJobWithDodging
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.config import config
from pioreactor.config import temporary_config_changes
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.types import MQTTMessage
from pioreactor.utils import is_pio_job_running
from pioreactor.whoami import get_unit_name


@contextmanager
def temporary_config_section(config_parser, section):
    section_exists = config_parser.has_section(section)
    if not section_exists:
        config_parser.add_section(section)
    try:
        yield
    finally:
        if not section_exists:
            config_parser.remove_section(section)


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
    assert not is_pio_job_running("testjob")


def test_what_happens_when_an_error_occurs_in_init_but_we_dont_catch() -> None:
    class TestJob(BackgroundJob):
        job_name = "testjob"

        def __init__(self, unit: str, experiment: str) -> None:
            super(TestJob, self).__init__(unit=unit, experiment=experiment)
            raise ZeroDivisionError()

    exp = "test_what_happens_when_an_error_occurs_in_init_but_we_dont_catch"
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
    assert not is_pio_job_running("testjob")


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


def test_cleans_up_mqtt() -> None:
    class TestJob(BackgroundJob):
        job_name = "job"
        published_settings = {
            "readonly_attr": {
                "datatype": "float",
                "settable": False,
            },
        }

        def __init__(self, unit, experiment):
            super().__init__(unit=unit, experiment=experiment)
            self.readonly_attr = 1.0

    exp = "test_cleans_up_mqtt"

    with TestJob(unit=get_unit_name(), experiment=exp):
        msg = subscribe(f"pioreactor/+/{exp}/job/readonly_attr", timeout=0.5)
        assert msg is not None

        msg = subscribe(f"pioreactor/+/{exp}/job/$state", timeout=0.5)
        assert msg is not None

        pause()

    msg = subscribe(f"pioreactor/+/{exp}/job/readonly_attr", timeout=0.5)
    assert msg is None

    msg = subscribe(f"pioreactor/+/{exp}/job/$state", timeout=0.5)
    assert msg is not None


def test_dodging_order() -> None:
    with temporary_config_section(config, "just_pause.config"):
        with temporary_config_changes(
            config,
            [
                ("just_pause.config", "post_delay_duration", "0.75"),
                ("just_pause.config", "pre_delay_duration", "0.25"),
                ("just_pause.config", "enable_dodging_od", "1"),
            ],
        ):

            def post_cb(od_job, batched_readings, *args):
                od_job.logger.notice(f"Done OD Reading at {time.time()}")

            def pre_cb(od_job, *args):
                od_job.logger.notice(f"Start OD Reading at {time.time()}")

            ODReader.add_pre_read_callback(pre_cb)
            ODReader.add_post_read_callback(post_cb)

            class JustPause(BackgroundJobWithDodging):
                job_name = "just_pause"

                def __init__(self, enable_dodging_od) -> None:
                    super().__init__(
                        unit=get_unit_name(), experiment="test_dodging", enable_dodging_od=enable_dodging_od
                    )

                def action_to_do_before_od_reading(self) -> None:
                    self.logger.notice(f"   Pausing at {time.time()} 🛑")

                def action_to_do_after_od_reading(self) -> None:
                    self.logger.notice(f"   Unpausing at {time.time()} 🟢")

            with collect_all_logs_of_level(
                "NOTICE", unit=get_unit_name(), experiment="test_dodging"
            ) as bucket:
                with start_od_reading(
                    {"1": "90"},
                    interval=6,
                    unit=get_unit_name(),
                    experiment="test_dodging",
                    fake_data=True,
                ):
                    time.sleep(5)
                    with JustPause(
                        enable_dodging_od=config.getboolean("just_pause.config", "enable_dodging_od")
                    ):
                        time.sleep(26)
                        assert len(bucket) > 4, bucket

            ODReader._pre_read = []
            ODReader._post_read = []


def test_dodging_when_od_reading_stops_first() -> None:
    with temporary_config_section(config, "just_pause.config"):
        with temporary_config_changes(
            config,
            [
                ("just_pause.config", "post_delay_duration", "0.75"),
                ("just_pause.config", "pre_delay_duration", "0.25"),
                ("just_pause.config", "enable_dodging_od", "1"),
            ],
        ):

            class JustPause(BackgroundJobWithDodging):
                job_name = "just_pause"

                def __init__(self) -> None:
                    super().__init__(
                        unit=get_unit_name(), experiment="test_dodging_when_od_reading_stops_first"
                    )

                def action_to_do_before_od_reading(self) -> None:
                    self.logger.notice(f"   Pausing at {time.time()} 🛑")

                def action_to_do_after_od_reading(self) -> None:
                    self.logger.notice(f"   Unpausing at {time.time()} 🟢")

            st = start_od_reading(
                {"1": "90"},
                unit=get_unit_name(),
                experiment="test_dodging_when_od_reading_stops_first",
                fake_data=True,
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


def test_disabling_dodging() -> None:
    exp = "test_disabling_dodging"

    with temporary_config_section(config, "just_pause.config"):
        with temporary_config_changes(
            config,
            [
                ("just_pause.config", "post_delay_duration", "0.2"),
                ("just_pause.config", "pre_delay_duration", "0.1"),
                ("just_pause.config", "enable_dodging_od", "1"),
            ],
        ):

            class JustPause(BackgroundJobWithDodging):
                job_name = "just_pause"
                published_settings = {"test": {"datatype": "float", "settable": True}}

                def __init__(self, enable_dodging_od) -> None:
                    super().__init__(
                        unit=get_unit_name(), experiment=exp, enable_dodging_od=enable_dodging_od
                    )

                def action_to_do_before_od_reading(self) -> None:
                    self.test = False
                    self.logger.notice(f"Pausing, {self.test=}")

                def action_to_do_after_od_reading(self) -> None:
                    self.test = True
                    self.logger.notice(f"Unpausing, {self.test=}")

                def initialize_dodging_operation(self):
                    self.test = False
                    self.logger.info(f"initialize_dodging_operation, {self.test=}")

                def initialize_continuous_operation(self):
                    self.test = True
                    self.logger.info(f"initialize_continuous_operation, {self.test=}")

            with collect_all_logs_of_level("NOTICE", unit=get_unit_name(), experiment=exp) as bucket:
                with start_od_reading(
                    {"1": "90"},
                    interval=5,  # needed
                    unit=get_unit_name(),
                    experiment=exp,
                    fake_data=True,
                ):
                    time.sleep(2)
                    with JustPause(
                        enable_dodging_od=config.getboolean("just_pause.config", "enable_dodging_od")
                    ) as jp:
                        assert set(jp.published_settings.keys()) == set(
                            ["test", "state", "enable_dodging_od", "currently_dodging_od"]
                        )
                        time.sleep(20)

                        assert len(bucket) == 7

                        jp.set_enable_dodging_od(False)
                        assert jp.test
                        time.sleep(20)

                        jp.set_enable_dodging_od(True)
                        assert not jp.test
                        time.sleep(3)


def test_disabled_dodging_will_start_continuous_operation() -> None:
    exp = "test_disabled_dodging_will_start_action_to_do_after_od_reading"
    with temporary_config_section(config, "just_pause.config"):
        with temporary_config_changes(
            config,
            [
                ("just_pause.config", "post_delay_duration", "0.2"),
                ("just_pause.config", "pre_delay_duration", "0.1"),
                ("just_pause.config", "enable_dodging_od", "0"),
            ],
        ):

            class JustPause(BackgroundJobWithDodging):
                job_name = "just_pause"

                def __init__(self) -> None:
                    super().__init__(unit=get_unit_name(), experiment=exp)

                def initialize_dodging_operation(self) -> None:
                    self.logger.notice("NOPE")

                def initialize_continuous_operation(self) -> None:
                    self.logger.notice("OK")

            with collect_all_logs_of_level("NOTICE", unit=get_unit_name(), experiment=exp) as bucket:
                with JustPause():
                    time.sleep(5)
                assert any("OK" in b["message"] for b in bucket)
                assert all("NOPE" not in b["message"] for b in bucket)


def test_subclasses_provide_a_unique_job_name_for_contrib():
    with pytest.raises(NameError):

        class TestJobBad(BackgroundJobContrib):
            def __init__(self, unit: str, experiment: str) -> None:
                super(TestJobBad, self).__init__(unit=unit, experiment=experiment, plugin_name="test")

    class TestJobOkay(BackgroundJobContrib):
        job_name = "test_job"

        def __init__(self, unit: str, experiment: str) -> None:
            super(TestJobOkay, self).__init__(unit=unit, experiment=experiment, plugin_name="test")
