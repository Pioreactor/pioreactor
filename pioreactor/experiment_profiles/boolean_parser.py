# -*- coding: utf-8 -*-
# mypy: ignore-errors
# flake8: noqa
from __future__ import annotations

from msgspec import DecodeError
from msgspec.json import decode

from .sly import Lexer
from .sly import Parser
from pioreactor.pubsub import subscribe
from pioreactor.whoami import get_latest_experiment_name


def convert_string(input_str: str) -> bool | float | str:
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


class BoolLexer(Lexer):
    # != is the same as not !=
    tokens = {
        NAME,
        AND,
        OR,
        NOT,
        EQUAL,
        LESS_THAN,
        GREATER_THAN,
        LESS_THAN_OR_EQUAL,
        GREATER_THAN_OR_EQUAL,
        NUMBER,
        UNIT_JOB_SETTING,
    }
    ignore = " \t"

    # Tokens
    UNIT_JOB_SETTING = r"([a-zA-Z_][a-zA-Z0-9_]*\.){2,}[a-zA-Z_][a-zA-Z0-9_]*"

    NAME = r"[a-zA-Z_][a-zA-Z0-9_]*"
    NAME["and"] = AND
    NAME["or"] = OR
    NAME["not"] = NOT

    # Comparison Operators
    LESS_THAN_OR_EQUAL = r"<="
    GREATER_THAN_OR_EQUAL = r">="
    EQUAL = r"=="
    LESS_THAN = r"<"
    GREATER_THAN = r">"

    NUMBER = r"[+-]?([0-9]*[.])?[0-9]+"  # decimal number

    # Special symbols
    literals = {"(", ")"}


class BoolParser(Parser):
    tokens = BoolLexer.tokens

    precedence = (
        ("left", AND, OR),
        ("right", NOT),
        ("nonassoc", LESS_THAN, EQUAL, GREATER_THAN),
    )

    @_("expr AND expr", "expr OR expr")
    def expr(self, p):
        if p[1] == "and":
            return p.expr0 and p.expr1
        elif p[1] == "or":
            return p.expr0 or p.expr1

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

    @_("NAME")
    def expr(self, p):
        if p.NAME == "True":
            return True
        elif p.NAME == "False":
            return False
        else:
            return p.NAME

    @_('"(" expr ")"')
    def expr(self, p):
        return p.expr

    @_("NUMBER")
    def expr(self, p):
        return float(p.NUMBER)

    @_("UNIT_JOB_SETTING")
    def expr(self, p) -> bool | float | str:
        # TODO: how does this work for common blocks?

        unit, job, setting, *keys = p.UNIT_JOB_SETTING.split(".")
        experiment = get_latest_experiment_name()
        result = subscribe(f"pioreactor/{unit}/{experiment}/{job}/{setting}", timeout=3)

        if result:
            # error handling here
            try:
                data_blob = decode(result.payload)
            except DecodeError:
                # just a string?
                return result.payload.decode()

            value = data_blob

            if len(keys) > 0:
                # its a nested json object, iteratively nest into it.
                for key in keys:
                    value = value[key]

            return convert_string(value)

        else:
            raise ValueError(f"{p.UNIT_JOB_SETTING} does not exist.")


def parse_profile_if_directive_to_bool(directive: str) -> bool:
    lexer = BoolLexer()
    parser = BoolParser()
    return parser.parse(lexer.tokenize(directive))
