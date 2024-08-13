# -*- coding: utf-8 -*-
# mypy: ignore-errors
# flake8: noqa
from __future__ import annotations

import math
from random import random

from msgspec import DecodeError
from msgspec.json import decode

from .sly import Lexer
from .sly import Parser
from pioreactor.exc import MQTTValueError
from pioreactor.pubsub import subscribe
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import is_active


def convert_string(input_str: str) -> int | bool | float | str:
    # Try to convert to float
    try:
        return float(input_str)
    except ValueError:
        pass

    # Try to convert to boolean
    if input_str.lower() == "true":
        return True
    elif input_str.lower() == "false":
        return False

    # Return string if other conversions fail
    return input_str


class ProfileLexer(Lexer):
    # != is the same as not
    tokens = {
        NAME,
        AND,
        OR,
        NOT,
        EQUAL,
        PLUS,
        MINUS,
        TIMES,
        DIVIDE,
        EXPONENT,
        LESS_THAN,
        GREATER_THAN,
        LESS_THAN_OR_EQUAL,
        GREATER_THAN_OR_EQUAL,
        NUMBER,
        UNIT_JOB_SETTING,
        COMMON_JOB_SETTING,
        FUNCTION,
    }
    ignore = " \t"

    # Tokens
    UNIT_JOB_SETTING = (
        r"([a-zA-Z_\$][a-zA-Z0-9_]*(\(\))?:){2,}([a-zA-Z_\$][a-zA-Z0-9_]*\.)*[a-zA-Z_\$][a-zA-Z0-9_]*"
    )
    COMMON_JOB_SETTING = r"::([a-zA-Z_\$][a-zA-Z0-9_]*:)([a-zA-Z_\$][a-zA-Z0-9_]*\.)*[a-zA-Z_\$][a-zA-Z0-9_]*"

    FUNCTION = r"[a-zA-Z_$][a-zA-Z0-9_]*\(\)"

    NAME = r"[a-zA-Z_$][a-zA-Z0-9_]*"
    NAME["and"] = AND
    NAME["or"] = OR
    NAME["not"] = NOT

    # Arithmetic Operators
    EXPONENT = r"\*\*"  # Regular expression for exponentiation
    PLUS = r"\+"
    MINUS = r"-"
    TIMES = r"\*"
    DIVIDE = r"/"

    # Comparison Operators
    LESS_THAN_OR_EQUAL = r"<="
    GREATER_THAN_OR_EQUAL = r">="
    EQUAL = r"=="
    LESS_THAN = r"<"
    GREATER_THAN = r">"

    NUMBER = r"[+-]?([0-9]*[.])?[0-9]+"  # decimal number

    # Special symbols
    literals = {"(", ")"}


class ProfileParser(Parser):

    """
    you can pass in an variable env that can dynamically populate data, ex:

    `unit()`

    will be replaced by env['unit']

    """

    def __init__(self, env=None):
        if env:
            self.ENV = env
        else:
            self.ENV = dict()

    tokens = ProfileLexer.tokens

    precedence = (
        ("left", AND, OR),
        ("right", NOT),
        ("nonassoc", LESS_THAN, EQUAL, GREATER_THAN),
        ("right", UMINUS),
        ("left", PLUS, MINUS),
        ("left", TIMES, DIVIDE),
        ("right", EXPONENT),
    )

    @_("expr AND expr", "expr OR expr")
    def expr(self, p):
        if p[1] == "and":
            return p.expr0 and p.expr1
        elif p[1] == "or":
            return p.expr0 or p.expr1

    @_("PLUS expr %prec UMINUS", "MINUS expr %prec UMINUS")
    def expr(self, p):
        if p[0] == "+":
            return p.expr
        elif p[0] == "-":
            return -p.expr

    @_("expr EXPONENT expr")  # Add rule for exponentiation
    def expr(self, p):
        return p.expr0**p.expr1

    @_("expr PLUS expr", "expr MINUS expr", "expr TIMES expr", "expr DIVIDE expr")
    def expr(self, p):
        if p[1] == "+":
            return p.expr0 + p.expr1
        elif p[1] == "-":
            return p.expr0 - p.expr1
        elif p[1] == "*":
            return p.expr0 * p.expr1
        elif p[1] == "/":
            # Handle division by zero
            if p.expr1 == 0:
                raise ZeroDivisionError("Division by zero is not allowed.")
            return p.expr0 / p.expr1

    @_(
        "expr LESS_THAN expr",
        "expr EQUAL expr",
        "expr GREATER_THAN expr",
        "expr GREATER_THAN_OR_EQUAL expr",
        "expr LESS_THAN_OR_EQUAL expr",
    )
    def expr(self, p):
        if p[1] == "<":
            return p.expr0 < p.expr1
        elif p[1] == "==":
            return p.expr0 == p.expr1
        elif p[1] == ">":
            return p.expr0 > p.expr1
        elif p[1] == ">=":
            return p.expr0 >= p.expr1
        elif p[1] == "<=":
            return p.expr0 <= p.expr1

    @_("NOT expr")
    def expr(self, p):
        return not p.expr

    @_("FUNCTION")
    def expr(self, p):
        if p.FUNCTION == "random()":
            return random()
        elif p.FUNCTION == "unit()":
            return self.ENV["unit"]
        elif p.FUNCTION == "hours_elapsed()":
            return self.ENV["hours_elapsed"]
        elif p.FUNCTION == "experiment()":
            return self.ENV["experiment"]
        elif p.FUNCTION == "job_name()":
            return self.ENV["job_name"]
        else:
            raise ValueError(f"{p.FUNCTION} is not a valid function in profile expressions.")

    @_("NAME")
    def expr(self, p):
        if p.NAME.lower() == "true":
            return True
        elif p.NAME.lower() == "false":
            return False
        elif p.NAME in self.ENV:
            return self.ENV[p.NAME]
        else:
            return p.NAME

    @_('"(" expr ")"')
    def expr(self, p):
        return p.expr

    @_("NUMBER")
    def expr(self, p):
        return float(p.NUMBER)

    @_("UNIT_JOB_SETTING", "COMMON_JOB_SETTING")
    def expr(self, p) -> bool | float | str:
        if hasattr(p, "COMMON_JOB_SETTING"):
            data_string = p.COMMON_JOB_SETTING.replace("::", self.ENV["unit"] + ":")
        else:
            data_string = p.UNIT_JOB_SETTING

        unit, job, setting_keys = data_string.split(":")
        setting, *keys = setting_keys.split(".")

        # HACK
        if unit == "unit()":
            # technically, common mqtt expressions can use ::job:attr, or unit():job:attr - they are equivalent.
            unit = self.ENV["unit"]
        if job == "job_name()":
            job = self.ENV["job_name"]

        experiment = get_assigned_experiment_name(unit)

        if not is_active(unit):
            raise NotActiveWorkerError(f"Worker {unit} is not active.")

        result = subscribe(f"pioreactor/{unit}/{experiment}/{job}/{setting}", timeout=1)

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
                    value = value[key]

            return convert_string(value)

        else:
            raise MQTTValueError(
                f"{':'.join([unit, job, setting_keys])} does not exist for experiment `{experiment}`"
            )


def parse_profile_expression_to_bool(profile_string: str, env=None) -> bool:
    result = parse_profile_expression(profile_string, env=env)
    if result is None:
        # syntax error or something funky.
        raise SyntaxError(profile_string)
    else:
        return bool(result)


def parse_profile_expression(profile_string: str, env=None):
    lexer = ProfileLexer()
    parser = ProfileParser(env)
    r = parser.parse(lexer.tokenize(profile_string))
    return r


def check_syntax(profile_string: str) -> bool:
    try:
        list(ProfileLexer().tokenize(profile_string))  # materialize it to force error
        return True
    except Exception as e:
        return False
