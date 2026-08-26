# -*- coding: utf-8 -*-
import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.base import BackgroundJobContrib
from pioreactor.background_jobs.base import BackgroundJobWithDodging
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.config import config
from pioreactor.config import temporary_config_changes
from pioreactor.exc import JobPresentError
from pioreactor.exc import NotActiveWorkerError
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import create_client
from pioreactor.pubsub import publish
from pioreactor.pubsub import QOS
from pioreactor.pubsub import subscribe
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.states import JobState
from pioreactor.types import MQTTMessage
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.job_manager import JobManager
from pioreactor.whoami import get_unit_name

from .utils import wait_for


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
    assert bj.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/background_job/$state/set", "sleeping")
    assert wait_for(lambda: bj.state == "sleeping", timeout=1.0)

    publish(f"pioreactor/{unit}/{exp}/background_job/$state/set", "ready")
    assert wait_for(lambda: bj.state == "ready", timeout=1.0)

    publish(f"pioreactor/{unit}/{exp}/background_job/$state/set", "init")
    assert wait_for(lambda: bj.state == "init", timeout=1.0)

    # it's kinda an antipattern to use this disconnect method from the main
    # thread. Better, if in the main thread and able to, to call bj.clean_up().
    # There's no 100% guarantee that this cleans up properly since it is called
    # in the sub thread, which means it's cleaning itself up?? Not clear!
    publish(f"pioreactor/{unit}/{exp}/background_job/$state/set", "disconnected")
    assert wait_for(lambda: bj.state == bj.DISCONNECTED, timeout=1.0)
    bj.clean_up()


def test_self_state_listener_uses_qos0() -> None:
    subscriptions_seen: list[tuple[list[str] | str, int]] = []

    class StateSubscriptionQosJob(BackgroundJob):
        job_name = "state_subscription_qos_job"

        def subscribe_and_callback(
            self,
            callback: Callable[[MQTTMessage], None],
            subscriptions: list[str] | str,
            allow_retained: bool = True,
            qos: int = QOS.EXACTLY_ONCE,
        ) -> None:
            subscriptions_seen.append((subscriptions, qos))
            super().subscribe_and_callback(callback, subscriptions, allow_retained, qos)

    unit = get_unit_name()
    experiment = "test_self_state_listener_uses_qos0"
    state_topic = f"pioreactor/{unit}/{experiment}/{StateSubscriptionQosJob.job_name}/$state"

    with StateSubscriptionQosJob(unit=unit, experiment=experiment):
        pass

    assert (state_topic, QOS.AT_MOST_ONCE) in subscriptions_seen


def test_disconnected_state_is_terminal() -> None:
    with BackgroundJob(
        unit=get_unit_name(),
        experiment="test_disconnected_state_is_terminal",
    ) as job:
        job.set_state(job.DISCONNECTED)
        job.set_state(job.SLEEPING)

        assert job.state == job.DISCONNECTED


def test_job_manager_cleanup_failure_does_not_prevent_mqtt_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with BackgroundJob(
        unit=get_unit_name(),
        experiment="test_job_manager_cleanup_failure_does_not_prevent_mqtt_shutdown",
    ) as job:
        sub_client_shutdown = MagicMock(wraps=job.sub_client.shutdown)
        pub_client_shutdown = MagicMock(wraps=job.pub_client.shutdown)
        monkeypatch.setattr(
            job,
            "_remove_from_job_manager",
            MagicMock(side_effect=RuntimeError("forced job-manager cleanup failure")),
        )
        monkeypatch.setattr(job.sub_client, "shutdown", sub_client_shutdown)
        monkeypatch.setattr(job.pub_client, "shutdown", pub_client_shutdown)

    sub_client_shutdown.assert_called_once_with()
    pub_client_shutdown.assert_called_once_with()
    assert job._is_cleaned_up


def test_back_to_back_qos1_state_commands_retain_disconnected_after_cleanup() -> None:
    unit = get_unit_name()
    experiment = "test_back_to_back_qos1_state_commands_retain_disconnected_after_cleanup"
    state_topic = f"pioreactor/{unit}/{experiment}/background_job/$state"
    control_client = create_client()

    try:
        with BackgroundJob(unit=unit, experiment=experiment) as job:
            sleeping = control_client.publish(
                f"{state_topic}/set",
                job.SLEEPING,
                qos=QOS.AT_LEAST_ONCE,
            )
            disconnected = control_client.publish(
                f"{state_topic}/set",
                job.DISCONNECTED,
                qos=QOS.AT_LEAST_ONCE,
            )
            sleeping.wait_for_publish(timeout=5)
            disconnected.wait_for_publish(timeout=5)
            job.block_until_disconnected()

        retained_state = subscribe(
            state_topic,
            timeout=2,
            qos=QOS.AT_LEAST_ONCE,
        )

        assert retained_state is not None
        assert retained_state.payload.decode() == job.DISCONNECTED
    finally:
        control_client.shutdown()


def test_block_until_ready_returns_current_readiness() -> None:
    debug_messages: list[str] = []

    class FakeLogger:
        def debug(self, message: str) -> None:
            debug_messages.append(message)

    job = object.__new__(BackgroundJob)
    object.__setattr__(job, "logger", FakeLogger())

    object.__setattr__(job, "state", job.READY)
    assert job.block_until_ready(timeout=0.0)

    object.__setattr__(job, "state", job.SLEEPING)
    assert not job.block_until_ready(timeout=-1.0)
    assert debug_messages == ["Timed out waiting for READY."]


def test_general_passive_listeners_start_after_subclass_constructor_finishes() -> None:
    values_seen_by_listener: list[str] = []
    reconnect_readiness_seen_by_listener: list[bool] = []

    class ConstructorDependentJob(BackgroundJob):
        job_name = "constructor_dependent_job"

        def __init__(self, unit: str, experiment: str) -> None:
            super().__init__(unit=unit, experiment=experiment)
            self.constructor_value = "ready"

        def _start_general_passive_listeners(self) -> None:
            super()._start_general_passive_listeners()
            values_seen_by_listener.append(self.constructor_value)
            reconnect_readiness_seen_by_listener.append(self._reconnect_callbacks_ready)

    with ConstructorDependentJob(
        unit=get_unit_name(),
        experiment="test_general_passive_listeners_start_after_subclass_constructor_finishes",
    ):
        pass

    assert values_seen_by_listener == ["ready"]
    assert reconnect_readiness_seen_by_listener == [True]


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
        pass

    assert wait_for(lambda: len(states) == 3, timeout=1.0)
    assert len(states) == 3
    assert states == ["init", "ready", "disconnected"]


@pytest.mark.flakey
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

    assert wait_for(lambda: len(bucket) >= 2, timeout=3.0)
    assert len(bucket) == 2


def test_error_in_subscribe_and_callback_is_logged() -> None:
    class TestJob(BackgroundJob):
        job_name = "test_job"

        def start_passive_listeners(self) -> None:
            self.subscribe_and_callback(self.callback, "pioreactor/testing/subscription")

        def callback(self, msg: MQTTMessage) -> None:
            print(1 / 0)

    experiment = "test_error_in_subscribe_and_callback_is_logged"

    with collect_all_logs_of_level("ERROR", get_unit_name(), experiment) as error_logs:
        with TestJob(unit=get_unit_name(), experiment=experiment):
            publish("pioreactor/testing/subscription", "test", retain=False)
            assert wait_for(lambda: len(error_logs) > 0, timeout=1.0)

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

    assert wait_for(lambda: bool(state) and state[-1] == "disconnected", timeout=1.0)
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

    assert wait_for(lambda: bool(state) and state[-1] == "disconnected", timeout=1.0)
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
        assert wait_for(lambda: tj.called_on_ready_to_sleeping, timeout=1.0)
        assert wait_for(lambda: tj.called_on_sleeping, timeout=1.0)
        assert tj.called_on_ready_to_sleeping
        assert tj.called_on_sleeping

        publish(f"pioreactor/{unit}/{exp}/{tj.job_name}/$state/set", tj.READY)
        assert wait_for(lambda: tj.called_on_sleeping_to_ready, timeout=1.0)
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


def test_settable_published_setting_requires_supported_datatype() -> None:
    class TestJob(BackgroundJob):
        job_name = "job"
        published_settings = {
            "growth_rate": {
                "datatype": "GrowthRate",
                "settable": True,
            },
        }

    with pytest.raises(ValueError, match="unsupported datatype"):
        with TestJob(
            unit=get_unit_name(),
            experiment="test_settable_published_setting_requires_supported_datatype",
        ):
            pass


def test_readonly_published_setting_allows_rich_datatype() -> None:
    BackgroundJob._check_published_settings({"growth_rate": {"datatype": "GrowthRate", "settable": False}})


def test_dynamically_added_settable_setting_requires_supported_datatype() -> None:
    with BackgroundJob(
        unit=get_unit_name(),
        experiment="test_dynamically_added_settable_setting_requires_supported_datatype",
    ) as job:
        with pytest.raises(ValueError, match="unsupported datatype"):
            job.add_to_published_settings("growth_rate", {"datatype": "GrowthRate", "settable": True})


@pytest.mark.parametrize(
    ("setting", "datatype", "payload", "previous_value"),
    [
        ("float_setting", "float", b"invalid", 1.5),
        ("integer_setting", "integer", b"1.5", 2),
        ("boolean_setting", "boolean", b"invalid", True),
        ("json_setting", "json", b"{", {"value": 1}),
    ],
)
def test_invalid_setter_payload_does_not_mutate_setting(
    setting: str, datatype: str, payload: bytes, previous_value: object
) -> None:
    job = object.__new__(BackgroundJob)
    job.published_settings = {setting: {"datatype": datatype, "settable": True}}  # type: ignore
    job.logger = MagicMock()
    object.__setattr__(job, setting, previous_value)
    message = MQTTMessage()
    message.topic = f"pioreactor/unit/experiment/job/{setting}/set"
    message.payload = payload

    job._set_attr_from_message(message)

    assert getattr(job, setting) == previous_value
    job.logger.warning.assert_called_once()


@pytest.mark.flakey
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

    assert wait_for(lambda: len(logs) > 0, timeout=3.0)
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
        pass

    msg = subscribe(
        f"pioreactor/{get_unit_name()}/{exp}/test_job/persist_this",
        timeout=0.5,
    )
    assert msg is not None
    assert msg.payload.decode() == "persist_this"

    msg = subscribe(
        f"pioreactor/{get_unit_name()}/{exp}/test_job/dont_persist_this",
        timeout=0.5,
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

    msg = subscribe(f"pioreactor/+/{exp}/job/readonly_attr", timeout=0.5)
    assert msg is None

    msg = subscribe(f"pioreactor/+/{exp}/job/$state", timeout=0.5)
    assert msg is not None


def test_clear_caches_doesnt_unpublish_settings_without_values(monkeypatch) -> None:
    recorded_upserts: list[tuple[str, object]] = []
    original_upsert = JobManager.upsert_setting

    def tracking_upsert(self, job_id, setting, value):
        recorded_upserts.append((setting, value))
        return original_upsert(self, job_id, setting, value)

    monkeypatch.setattr(JobManager, "upsert_setting", tracking_upsert)

    class OptionalSettingJob(BackgroundJob):
        job_name = "optional_setting_job"
        published_settings = {
            "optional_setting": {
                "datatype": "float",
                "settable": True,
            },
        }

        def __init__(self, unit, experiment) -> None:
            self.unpublished_settings: list[str] = []
            super().__init__(unit=unit, experiment=experiment)

        def _unpublish_setting(self, setting: str) -> None:
            self.unpublished_settings.append(setting)
            super()._unpublish_setting(setting)

    exp = "test_clear_caches_doesnt_unpublish_settings_without_values"
    unit = get_unit_name()

    with OptionalSettingJob(unit=unit, experiment=exp) as job:
        pass

    assert "optional_setting" not in job.unpublished_settings
    assert all(setting != "optional_setting" for setting, _ in recorded_upserts)


def test_duplicate_job_cannot_start_while_existing_instance_is_running() -> None:
    class DuplicateJob(BackgroundJob):
        job_name = "duplicate_job_guard"

    exp = "test_duplicate_job_cannot_start_while_existing_instance_is_running"
    unit = get_unit_name()

    with DuplicateJob(unit=unit, experiment=exp):
        with pytest.raises(JobPresentError):
            DuplicateJob(unit=unit, experiment=exp)


def test_clean_up_still_disconnects_when_ready_to_disconnected_hook_errors() -> None:
    class TestJob(BackgroundJob):
        job_name = "hook_error_on_disconnect"

        def on_ready_to_disconnected(self) -> None:
            raise RuntimeError("disconnect hook failed")

    exp = "test_clean_up_still_disconnects_when_ready_to_disconnected_hook_errors"
    unit = get_unit_name()

    job = TestJob(unit=unit, experiment=exp)
    job.clean_up()

    state_msg = subscribe(
        f"pioreactor/{unit}/{exp}/{job.job_name}/$state",
        timeout=1.0,
    )

    assert job.state == job.DISCONNECTED
    assert job._blocking_event.is_set()
    assert state_msg is not None
    assert state_msg.payload.decode() == job.DISCONNECTED


def test_constructor_failure_after_parent_init_cleans_up_job() -> None:
    class FailingAfterParentInitJob(BackgroundJob):
        job_name = "failing_after_parent_init"
        on_disconnected_called = False

        def __init__(self, unit: str, experiment: str) -> None:
            super().__init__(unit=unit, experiment=experiment)
            raise RuntimeError("failed after parent init")

        def on_disconnected(self) -> None:
            type(self).on_disconnected_called = True

    exp = "test_constructor_failure_after_parent_init_cleans_up_job"
    unit = get_unit_name()

    with pytest.raises(RuntimeError, match="failed after parent init"):
        FailingAfterParentInitJob(unit=unit, experiment=exp)

    assert FailingAfterParentInitJob.on_disconnected_called
    assert not is_pio_job_running("failing_after_parent_init")


def test_clean_up_can_be_called_twice() -> None:
    exp = "test_clean_up_can_be_called_twice"
    unit = get_unit_name()
    job = BackgroundJob(unit=unit, experiment=exp)

    job.clean_up()
    job.clean_up()

    assert job.state == job.DISCONNECTED
    assert job._blocking_event.is_set()
    assert not is_pio_job_running("background_job")


def test_clean_up_tolerates_pre_parent_init_failure() -> None:
    class FailingBeforeParentInitJob(BackgroundJob):
        job_name = "failing_before_parent_init"

        def __init__(self, unit: str, experiment: str) -> None:
            raise RuntimeError("failed before parent init")

    with pytest.raises(RuntimeError, match="failed before parent init"):
        FailingBeforeParentInitJob(
            unit=get_unit_name(), experiment="test_clean_up_tolerates_pre_parent_init_failure"
        )


def test_dodging_jobs_respect_inactive_worker_guard(monkeypatch) -> None:
    monkeypatch.setattr(
        "pioreactor.background_jobs.base.is_active",
        lambda unit: unit != "notactiveworker",
    )

    with temporary_config_section(config, "inactive_dodging_job.config"):

        class InactiveDodgingJob(BackgroundJobWithDodging):
            job_name = "inactive_dodging_job"

            def __init__(self, unit: str, experiment: str) -> None:
                super().__init__(unit=unit, experiment=experiment)

        job = None
        try:
            job = InactiveDodgingJob(
                unit="notactiveworker",
                experiment="test_dodging_jobs_respect_inactive_worker_guard",
            )
        except NotActiveWorkerError:
            pass
        else:
            try:
                pytest.fail("Expected dodging jobs to reject inactive workers.")
            finally:
                job.clean_up()


@pytest.mark.parametrize(
    ("enable_dodging_od", "od_state", "expected"),
    [
        (False, None, False),
        (False, JobState.INIT, False),
        (False, JobState.READY, False),
        (False, JobState.SLEEPING, False),
        (False, JobState.LOST, False),
        (False, JobState.DISCONNECTED, False),
        (True, None, False),
        (True, JobState.INIT, True),
        (True, JobState.READY, True),
        (True, JobState.SLEEPING, True),
        (True, JobState.LOST, False),
        (True, JobState.DISCONNECTED, False),
    ],
)
def test_desired_dodging_mode_matches_od_state_invariant(
    enable_dodging_od: bool, od_state: JobState | None, expected: bool
) -> None:
    job = object.__new__(BackgroundJobWithDodging)

    assert job._desired_dodging_mode(enable_dodging_od, od_state) is expected


def test_dodging_persists_when_second_od_reader_start_fails() -> None:
    exp = "test_dodging_persists_when_second_od_reader_start_fails"
    unit = get_unit_name()

    with temporary_config_section(config, "keep_dodging.config"):
        with temporary_config_changes(
            config,
            [
                ("keep_dodging.config", "post_delay_duration", "0.3"),
                ("keep_dodging.config", "pre_delay_duration", "0.3"),
                ("keep_dodging.config", "enable_dodging_od", "1"),
            ],
        ):

            class KeepDodging(BackgroundJobWithDodging):
                job_name = "keep_dodging"

                def __init__(self) -> None:
                    super().__init__(unit=unit, experiment=exp, enable_dodging_od=True)

                def action_to_do_before_od_reading(self) -> None:
                    self.logger.notice("before reading")

                def action_to_do_after_od_reading(self) -> None:
                    self.logger.notice("after reading")

            def wait_for(predicate, timeout=6.0) -> None:
                deadline = time.time() + timeout
                while time.time() < deadline:
                    if predicate():
                        return
                    time.sleep(0.2)
                raise AssertionError("predicate did not become True in time")

            with KeepDodging() as dodger:
                assert not dodger.currently_dodging_od

                with start_od_reading({"1": "90"}, interval=3, unit=unit, experiment=exp, fake_data=True):
                    wait_for(lambda: dodger.currently_dodging_od)
                    assert dodger.currently_dodging_od

                    interval_topic = f"pioreactor/{unit}/{exp}/od_reading/interval"
                    interval_msg = subscribe(interval_topic, timeout=1)
                    assert interval_msg is not None

                    with pytest.raises(JobPresentError):
                        start_od_reading({"1": "90"}, interval=3, unit=unit, experiment=exp, fake_data=True)

                    time.sleep(1)
                    assert dodger.currently_dodging_od
                    interval_msg = subscribe(interval_topic, timeout=1)
                    assert interval_msg is not None


def test_disabling_dodging_while_sleeping_stays_disabled_when_ready() -> None:
    class FakeTimer:
        def __init__(self) -> None:
            self.cancel_count = 0
            self.unpause_count = 0

        def cancel(self) -> None:
            self.cancel_count += 1

        def unpause(self) -> None:
            self.unpause_count += 1

    class FakeEvent:
        def __init__(self) -> None:
            self.clear_count = 0
            self.set_count = 0

        def clear(self) -> None:
            self.clear_count += 1

        def set(self) -> None:
            self.set_count += 1

    class FakeLogger:
        def debug(self, *args: object, **kwargs: object) -> None:
            pass

        def info(self, *args: object, **kwargs: object) -> None:
            pass

    class SleepingDodger(BackgroundJobWithDodging):
        def initialize_continuous_operation(self) -> None:
            self.continuous_operation_calls += 1

    timer = FakeTimer()
    event = FakeEvent()
    job = object.__new__(SleepingDodger)
    object.__setattr__(job, "continuous_operation_calls", 0)
    object.__setattr__(job, "logger", FakeLogger())
    object.__setattr__(job, "state", job.SLEEPING)
    object.__setattr__(job, "enable_dodging_od", True)
    object.__setattr__(job, "currently_dodging_od", True)
    object.__setattr__(job, "_dodging_init_called_once", True)
    object.__setattr__(job, "_dodging_mode_startup_pending", False)
    object.__setattr__(job, "sneak_in_timer", timer)
    object.__setattr__(job, "_event_is_dodging_od", event)

    job.set_enable_dodging_od(False)

    assert not job.currently_dodging_od
    assert timer.cancel_count == 1
    assert job.continuous_operation_calls == 0

    job.on_sleeping_to_ready()

    assert job.continuous_operation_calls == 0
    assert timer.unpause_count == 0

    job.ready()

    assert job.continuous_operation_calls == 1


def test_dodging_post_init_timer_setup_failure_cleans_up_running_job(monkeypatch) -> None:
    class FakePublishResult:
        def wait_for_publish(self, timeout: float | None = None) -> None:
            pass

    class FakeClient:
        def publish(self, *args: object, **kwargs: object) -> FakePublishResult:
            return FakePublishResult()

        def is_connected(self) -> bool:
            return True

        def message_callback_add(self, *args: object, **kwargs: object) -> None:
            pass

        def subscribe(self, *args: object, **kwargs: object) -> None:
            pass

        def shutdown(self) -> None:
            pass

    def raise_missing_od_setting(
        self: JobManager, job_name: str, setting: str, timeout: float | None = None
    ) -> object:
        raise NameError("missing OD timing setting")

    monkeypatch.setattr("pioreactor.background_jobs.base.is_active", lambda unit: True)
    monkeypatch.setattr("pioreactor.background_jobs.base.is_pio_job_running", lambda job_name: True)
    monkeypatch.setattr(JobManager, "get_setting_from_running_job", raise_missing_od_setting)

    class FailingDodgingSetup(BackgroundJobWithDodging):
        job_name = "failing_dodging_setup"

        def __init__(self) -> None:
            super().__init__(
                unit=get_unit_name(),
                experiment="test_dodging_post_init_timer_setup_failure_cleans_up_running_job",
                enable_dodging_od=True,
            )

        def _create_pub_client(self) -> FakeClient:
            return FakeClient()

        def _create_sub_client(self) -> FakeClient:
            return FakeClient()

    with temporary_config_section(config, "failing_dodging_setup.config"):
        try:
            with pytest.raises(NameError, match="missing OD timing setting"):
                FailingDodgingSetup()

            assert not is_pio_job_running("failing_dodging_setup")
        finally:
            with JobManager() as jm:
                job_id = jm.get_running_job_id("failing_dodging_setup")
                if job_id is not None:
                    jm.set_not_running(job_id)

            logger = logging.getLogger("failing_dodging_setup")
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()


@pytest.mark.flakey
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
                        assert wait_for(lambda: len(bucket) > 4, timeout=6.0), bucket

            ODReader._pre_read = []
            ODReader._post_read = []


@pytest.mark.slow
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


@pytest.mark.flakey
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
                        enable_dodging_od=config.getboolean("just_pause.config", "enable_dodging_od"),
                    ) as jp:
                        assert set(jp.published_settings.keys()) == set(
                            ["test", "state", "enable_dodging_od", "currently_dodging_od"]
                        )
                        time.sleep(20)

                        assert wait_for(lambda: len(bucket) >= 7, timeout=6.0)
                        assert len(bucket) == 7

                        jp.set_enable_dodging_od(False)
                        assert jp.test
                        time.sleep(20)

                        jp.set_enable_dodging_od(True)
                        assert not jp.test
                        time.sleep(3)


@pytest.mark.flakey
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
                assert wait_for(lambda: any("OK" in b["message"] for b in bucket), timeout=5.0)
            assert all("NOPE" not in b["message"] for b in bucket)


def test_subclasses_provide_a_unique_job_name_for_contrib() -> None:
    with pytest.raises(NameError):

        class TestJobBad(BackgroundJobContrib):
            def __init__(self, unit: str, experiment: str) -> None:
                super(TestJobBad, self).__init__(unit=unit, experiment=experiment, plugin_name="test")

    class TestJobOkay(BackgroundJobContrib):
        job_name = "test_job"

        def __init__(self, unit: str, experiment: str) -> None:
            super(TestJobOkay, self).__init__(unit=unit, experiment=experiment, plugin_name="test")
