# -*- coding: utf-8 -*-
import signal
from contextlib import redirect_stdout
from io import StringIO

import pytest
from pioreactor.utils import signal_handlers


def _install_fake_signal_backend(monkeypatch, initial_handler):
    state = {signal.SIGTERM: initial_handler}

    def fake_getsignal(signal_value):
        return state[signal_value]

    def fake_signal(signal_value, handler):
        state[signal_value] = handler
        return handler

    monkeypatch.setattr(signal_handlers.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(signal_handlers.signal, "signal", fake_signal)
    return state


def test_append_signal_handler_stacks_callbacks_and_calls_original_handler_after_callbacks(
    monkeypatch,
) -> None:
    events: list[str] = []

    def original_handler(*args):
        events.append(f"original:{args}")

    def first_callback(*args):
        events.append(f"first:{args}")

    def second_callback(*args):
        events.append(f"second:{args}")

    state = _install_fake_signal_backend(monkeypatch, original_handler)

    signal_handlers.append_signal_handler(signal.SIGTERM, first_callback)
    signal_handlers.append_signal_handler(signal.SIGTERM, second_callback)

    handler = state[signal.SIGTERM]
    assert isinstance(handler, signal_handlers.callable_stack)
    assert handler.call_original_handler_after_callbacks is True

    handler("alpha")

    assert events == ["second:('alpha',)", "first:('alpha',)", "original:('alpha',)"]


def test_remove_signal_handler_restores_sig_dfl_after_last_callback_is_removed(
    monkeypatch,
) -> None:
    def first_callback(*args):
        pass

    state = _install_fake_signal_backend(monkeypatch, signal.SIG_DFL)

    signal_handlers.append_signal_handler(signal.SIGTERM, first_callback)

    handler = state[signal.SIGTERM]
    assert isinstance(handler, signal_handlers.callable_stack)

    signal_handlers.remove_signal_handler(signal.SIGTERM, first_callback)

    assert state[signal.SIGTERM] is signal.SIG_DFL


def test_remove_signal_handler_keeps_stack_until_all_callbacks_are_removed(
    monkeypatch,
) -> None:
    def original_handler(*args):
        pass

    def first_callback(*args):
        pass

    def second_callback(*args):
        pass

    state = _install_fake_signal_backend(monkeypatch, original_handler)

    signal_handlers.append_signal_handler(signal.SIGTERM, first_callback)
    signal_handlers.append_signal_handler(signal.SIGTERM, second_callback)

    signal_handlers.remove_signal_handler(signal.SIGTERM, second_callback)

    handler = state[signal.SIGTERM]
    assert isinstance(handler, signal_handlers.callable_stack)
    assert handler.is_empty is False

    signal_handlers.remove_signal_handler(signal.SIGTERM, first_callback)

    assert state[signal.SIGTERM] is original_handler


def greet(name):
    print(f"Hello, {name}!")


def goodbye(name):
    print(f"Goodbye, {name}!")


def test_callable_stack_append_and_call() -> None:
    my_stack = signal_handlers.callable_stack()
    my_stack.append(greet)
    my_stack.append(goodbye)

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == "Goodbye, Alice!\nHello, Alice!\n"


def test_callable_stack_empty_call() -> None:
    def default_function(name):
        print(f"Default function called, {name}")

    my_stack = signal_handlers.callable_stack(default_function_if_empty=default_function)

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == "Default function called, Alice\n"


def test_callable_stack_no_default() -> None:
    my_stack = signal_handlers.callable_stack()

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == ""


@pytest.mark.parametrize(
    "functions,expected_output",
    [
        ([greet], "Hello, Alice!\n"),
        ([goodbye], "Goodbye, Alice!\n"),
        ([greet, goodbye], "Goodbye, Alice!\nHello, Alice!\n"),
    ],
)
def test_callable_stack_multiple_append_and_call(functions, expected_output) -> None:
    my_stack = signal_handlers.callable_stack()

    for function in functions:
        my_stack.append(function)

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == expected_output


def test_callable_stack_remove_returns_true_and_removes_last_matching_callable() -> None:
    my_stack = signal_handlers.callable_stack()
    my_stack.append(greet)
    my_stack.append(goodbye)
    my_stack.append(greet)

    assert my_stack.remove(greet) is True

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == "Goodbye, Alice!\nHello, Alice!\n"


def test_callable_stack_remove_returns_false_when_callable_is_missing() -> None:
    my_stack = signal_handlers.callable_stack()
    my_stack.append(greet)

    assert my_stack.remove(goodbye) is False

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == "Hello, Alice!\n"
