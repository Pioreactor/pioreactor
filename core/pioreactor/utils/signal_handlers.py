# -*- coding: utf-8 -*-
import signal
from typing import Any
from typing import Callable


class callable_stack:
    """
    A class for managing a stack of callable objects in Python.

    Example:
    >>> def greet(name):
    ... print(f"Hello, {name}!")
    ...
    >>> def goodbye(name):
    ... print(f"Goodbye, {name}!")
    ...
    >>> my_stack = callable_stack()
    >>> my_stack.append(greet)
    >>> my_stack.append(goodbye)
    >>> my_stack('Alice')
    Goodbye, Alice!
    Hello, Alice!
    """

    def __init__(
        self,
        default_function_if_empty: Callable[..., None] = lambda *args: None,
        original_handler: Any = signal.SIG_DFL,
        call_original_handler_after_callbacks: bool = False,
    ) -> None:
        self._callables: list[Callable[..., None]] = []
        self.default = default_function_if_empty
        self.original_handler = original_handler
        self.call_original_handler_after_callbacks = call_original_handler_after_callbacks

    def append(self, function: Callable[..., None]) -> None:
        self._callables.append(function)

    def remove(self, function: Callable[..., None]) -> bool:
        for index in range(len(self._callables) - 1, -1, -1):
            if self._callables[index] == function:
                del self._callables[index]
                return True

        return False

    @property
    def is_empty(self) -> bool:
        return not self._callables

    def __call__(self, *args: object) -> None:
        if not self._callables:
            self.default(*args)
            return

        while self._callables:
            function = self._callables.pop()
            function(*args)

        if self.call_original_handler_after_callbacks and callable(self.original_handler):
            self.original_handler(*args)


def append_signal_handler(signal_value: signal.Signals, new_callback: Callable[..., None]) -> None:
    """
    The current api of signal.signal is a global stack of size 1, so if
    we have multiple jobs started in the same python process, we
    need them all to respect each others signal.
    """
    current_callback = signal.getsignal(signal_value)

    if callable(current_callback):
        if isinstance(current_callback, callable_stack):
            current_callback.append(new_callback)
            signal.signal(signal_value, current_callback)
        else:
            stack = callable_stack(
                signal.default_int_handler,
                original_handler=current_callback,
                call_original_handler_after_callbacks=True,
            )
            stack.append(new_callback)
            signal.signal(signal_value, stack)
    elif (current_callback is signal.SIG_DFL) or (current_callback is signal.SIG_IGN):
        stack = callable_stack(signal.default_int_handler, original_handler=current_callback)
        stack.append(new_callback)
        signal.signal(signal_value, stack)
    elif current_callback is None:
        signal.signal(
            signal_value,
            callable_stack(signal.default_int_handler, original_handler=signal.SIG_DFL),
        )
    else:
        raise RuntimeError(f"Something is wrong. Observed {current_callback}.")


def append_signal_handlers(signal_value: signal.Signals, new_callbacks: list[Callable[..., None]]) -> None:
    for callback in new_callbacks:
        append_signal_handler(signal_value, callback)


def remove_signal_handler(signal_value: signal.Signals, callback_to_remove: Callable[..., None]) -> None:
    current_callback = signal.getsignal(signal_value)

    if not isinstance(current_callback, callable_stack):
        return

    current_callback.remove(callback_to_remove)

    if current_callback.is_empty:
        signal.signal(signal_value, current_callback.original_handler)
    else:
        signal.signal(signal_value, current_callback)


def remove_signal_handlers(
    signal_value: signal.Signals, callbacks_to_remove: list[Callable[..., None]]
) -> None:
    for callback in callbacks_to_remove:
        remove_signal_handler(signal_value, callback)
