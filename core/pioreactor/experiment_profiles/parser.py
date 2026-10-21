# -*- coding: utf-8 -*-
import operator
import re
from collections.abc import Callable
from random import random
from typing import Any

from msgspec import DecodeError
from msgspec import Struct
from msgspec.json import decode
from pioreactor.exc import MQTTValueError
from pioreactor.exc import NotActiveWorkerError
from pioreactor.pubsub import subscribe
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import is_active


# Order matters: MQTT references and functions must precede bare names.
_TOKEN = re.compile(
    r"(?P<LOOKUP>([a-zA-Z_\$][a-zA-Z0-9_]*(\(\))?:){2}"
    r"([a-zA-Z_\$][a-zA-Z0-9_]*\.)*[a-zA-Z_\$][a-zA-Z0-9_]*)"
    r"|(?P<COMMON>::([a-zA-Z_\$][a-zA-Z0-9_]*:)"
    r"([a-zA-Z_\$][a-zA-Z0-9_]*\.)*[a-zA-Z_\$][a-zA-Z0-9_]*)"
    r"|(?P<FUNCTION>[a-zA-Z_$][a-zA-Z0-9_]*\(\))"
    r"|(?P<NAME>[a-zA-Z_$][a-zA-Z0-9_]*)"
    r"|(?P<OP>\*\*|<=|>=|==|[+*/<>()-])"
    r"|(?P<NUMBER>([0-9]*[.])?[0-9]+)"
    r"|(?P<SPACE>[ \t]+)"
)
# Equal left/right binding powers make exponentiation right-associative.
# Unary signs bind below exponentiation; not binds below comparisons.
_BINDING_POWER = {
    "<=": (5, 6),
    ">=": (5, 6),
    "or": (2, 3),
    "and": (3, 4),
    "<": (5, 6),
    "==": (5, 6),
    ">": (5, 6),
    "+": (7, 8),
    "-": (7, 8),
    "*": (8, 9),
    "/": (8, 9),
    "**": (10, 10),
}
_BINARY: dict[str, Callable[[Any, Any], Any]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "**": operator.pow,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    ">=": operator.ge,
    ">": operator.gt,
}


class Expression(Struct):
    kind: str
    value: str
    children: tuple["Expression", ...] = ()


class ProfileParser:
    """Build a tree without resolving names, invoking functions, or reading MQTT."""

    def __init__(self, source: str) -> None:
        self.tokens: list[tuple[str, str]] = []
        position = 0
        while position < len(source):
            match = _TOKEN.match(source, position)
            if match is None:
                raise SyntaxError(f"Invalid profile expression at position {position}: {source[position]!r}")
            kind, value = match.lastgroup, match.group()
            if kind != "SPACE":
                assert kind is not None
                self.tokens.append((kind, value))
            position = match.end()
        self.tokens.append(("EOF", ""))
        self.position = 0

    def parse(self) -> Expression:
        result = self.expression(0)
        if self.tokens[self.position][0] != "EOF":
            raise SyntaxError("Unexpected trailing token in profile expression.")
        return result

    def expression(self, minimum_power: int) -> Expression:
        kind, value = self.tokens[self.position]
        self.position += 1
        if value in ("+", "-", "not"):
            left = Expression("unary", value, (self.expression(4 if value == "not" else 9),))
        elif value == "(":
            left = self.expression(0)
            if self.tokens[self.position][1] != ")":
                raise SyntaxError("Expected ')' in profile expression.")
            self.position += 1
        elif kind in ("NUMBER", "NAME", "FUNCTION", "LOOKUP", "COMMON") and value not in ("and", "or"):
            left = Expression(kind, value)
        else:
            raise SyntaxError("Expected a value in profile expression.")

        previous_power = 0
        while (op := self.tokens[self.position][1]) in _BINDING_POWER:
            left_power, right_power = _BINDING_POWER[op]
            if left_power < minimum_power:
                break
            if previous_power == left_power == 5:
                raise SyntaxError("Comparisons cannot be chained without parentheses.")
            self.position += 1
            right = self.expression(right_power)
            left = Expression("binary", op, (left, right))
            previous_power = left_power
        return left


def evaluate(expression: Expression, env: dict[str, Any]) -> Any:
    kind, value = expression.kind, expression.value
    if kind == "binary":
        left = evaluate(expression.children[0], env)
        if value == "and":
            return left and evaluate(expression.children[1], env)
        if value == "or":
            return left or evaluate(expression.children[1], env)
        right = evaluate(expression.children[1], env)
        if value == "/" and right == 0:
            raise ZeroDivisionError("Division by zero is not allowed.")
        return _BINARY[value](left, right)
    if kind == "unary":
        operand = evaluate(expression.children[0], env)
        if value == "not":
            return not operand
        return -operand if value == "-" else +operand
    if kind == "NUMBER":
        return float(value)
    if kind == "NAME":
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        return env.get(value, value)
    if kind == "FUNCTION":
        if value == "random()":
            return random()
        if value in ("unit()", "hours_elapsed()", "experiment()", "job_name()"):
            return env[value[:-2]]
        raise ValueError(f"{value} is not a valid function in profile expressions.")
    return lookup_mqtt(value.replace("::", env["unit"] + ":") if kind == "COMMON" else value, env)


def convert_string(input_value: object) -> object:
    if not isinstance(input_value, str):
        return input_value

    # Try to convert to float
    try:
        return float(input_value)
    except ValueError:
        pass

    # Try to convert to boolean
    if input_value.lower() == "true":
        return True
    elif input_value.lower() == "false":
        return False

    # Return string if other conversions fail
    return input_value


def lookup_mqtt(data_string: str, env: dict[str, Any]) -> Any:
    unit, job, setting_keys = data_string.split(":")
    setting, *keys = setting_keys.split(".")

    # HACK
    if unit == "unit()":
        # technically, common mqtt expressions can use ::job:attr, or unit():job:attr - they are equivalent.
        unit = env["unit"]
    if job == "job_name()":
        job = env["job_name"]

    experiment = get_assigned_experiment_name(unit)

    if not is_active(unit):
        raise NotActiveWorkerError(f"Worker {unit} is not active.")

    result = subscribe(f"pioreactor/{unit}/{experiment}/{job}/{setting}", timeout=2.0)

    if result:
        # error handling here
        try:
            data_blob = decode(result.payload)
        except DecodeError:
            # just a string?
            return convert_string(result.payload.decode())

        value = data_blob

        if len(keys) > 0:
            # its a nested json object, iteratively nest into it.
            for key in keys:
                if not isinstance(value, dict):
                    raise TypeError(
                        f"Expression lookup `{data_string}` attempted nested key access `{key}` "
                        f"on a non-mapping value of type `{type(value).__name__}`."
                    )

                if key not in value:
                    available_keys = ", ".join(str(k) for k in value.keys())
                    raise KeyError(
                        f"Expression lookup `{data_string}` referenced missing nested key `{key}`. "
                        f"Available keys: [{available_keys}]"
                    )

                value = value[key]

        return convert_string(value)

    else:
        raise MQTTValueError(
            f"{':'.join([unit, job, setting_keys])} does not exist for experiment `{experiment}`"
        )


def parse_profile_expression_to_bool(profile_string: str, env: dict[str, Any] | None = None) -> bool:
    result = parse_profile_expression(profile_string, env=env)
    if result is None:
        raise SyntaxError(profile_string)
    return bool(result)


def parse_profile_expression(profile_string: str, env: dict[str, Any] | None = None) -> Any:
    return evaluate(ProfileParser(profile_string).parse(), env if env is not None else {})


def check_syntax(profile_string: str) -> bool:
    try:
        ProfileParser(profile_string).parse()
        return True
    except (SyntaxError, RecursionError):
        return False
