# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
#
# Copyright (C) 2016 - 2018
# David M. Beazley (Dabeaz LLC)
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name of the David Beazley or Dabeaz LLC may be used to
#   endorse or promote products derived from this software without
#  specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# -----------------------------------------------------------------------------
# mypy: ignore-errors
# flake8: noqa
import pytest
from pioreactor.experiment_profiles.sly import Lexer
from pioreactor.experiment_profiles.sly import Parser


class CalcLexer(Lexer):
    # Set of token names.   This is always required
    tokens = {ID, NUMBER, PLUS, MINUS, TIMES, DIVIDE, ASSIGN, COMMA}
    literals = {"(", ")"}

    # String containing ignored characters between tokens
    ignore = " \t"

    # Regular expression rules for tokens
    ID = r"[a-zA-Z_][a-zA-Z0-9_]*"
    PLUS = r"\+"
    MINUS = r"-"
    TIMES = r"\*"
    DIVIDE = r"/"
    ASSIGN = r"="
    COMMA = r","

    @_(r"\d+")
    def NUMBER(self, t):
        t.value = int(t.value)
        return t

    # Ignored text
    ignore_comment = r"\#.*"

    @_(r"\n+")
    def newline(self, t):
        self.lineno += t.value.count("\n")

    def error(self, t):
        self.errors.append(t.value[0])
        self.index += 1

    def __init__(self) -> None:
        self.errors = []


class CalcParser(Parser):
    tokens = CalcLexer.tokens

    precedence = (
        ("left", PLUS, MINUS),
        ("left", TIMES, DIVIDE),
        ("right", UMINUS),
    )

    def __init__(self) -> None:
        self.names = {}
        self.errors = []

    @_("ID ASSIGN expr")
    def statement(self, p):
        self.names[p.ID] = p.expr

    @_('ID "(" [ arglist ] ")"')
    def statement(self, p):
        return (p.ID, p.arglist)

    @_("expr { COMMA expr }")
    def arglist(self, p):
        return [p.expr0, *p.expr1]

    @_("expr")
    def statement(self, p):
        return p.expr

    @_("expr PLUS expr")
    def expr(self, p):
        return p.expr0 + p.expr1

    @_("expr MINUS expr")
    def expr(self, p):
        return p.expr0 - p.expr1

    @_("expr TIMES expr")
    def expr(self, p):
        return p.expr0 * p.expr1

    @_("expr DIVIDE expr")
    def expr(self, p):
        return p.expr0 / p.expr1

    @_("MINUS expr %prec UMINUS")
    def expr(self, p):
        return -p.expr

    @_('"(" expr ")"')
    def expr(self, p):
        return p.expr

    @_("NUMBER")
    def expr(self, p):
        return p.NUMBER

    @_("ID")
    def expr(self, p):
        try:
            return self.names[p.ID]
        except LookupError:
            self.errors.append(("undefined", p.ID))
            return 0

    def error(self, tok):
        self.errors.append(tok)


# Test basic recognition of various tokens and literals
def test_simple() -> None:
    lexer = CalcLexer()
    parser = CalcParser()

    result = parser.parse(lexer.tokenize("a = 3 + 4 * (5 + 6)"))
    assert result == None
    assert parser.names["a"] == 47

    result = parser.parse(lexer.tokenize("3 + 4 * (5 + 6)"))
    assert result == 47


def test_ebnf() -> None:
    lexer = CalcLexer()
    parser = CalcParser()
    result = parser.parse(lexer.tokenize("a()"))
    assert result == ("a", None)

    result = parser.parse(lexer.tokenize("a(2+3)"))
    assert result == ("a", [5])

    result = parser.parse(lexer.tokenize("a(2+3, 4+5)"))
    assert result == ("a", [5, 9])


def test_parse_error() -> None:
    lexer = CalcLexer()
    parser = CalcParser()

    result = parser.parse(lexer.tokenize("a 123 4 + 5"))
    assert result == 9
    assert len(parser.errors) == 1
    assert parser.errors[0].type == "NUMBER"
    assert parser.errors[0].value == 123


# TO DO:  Add tests
# - error productions
# - embedded actions
# - lineno tracking
# - various error cases caught during parser construction
