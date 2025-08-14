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
from __future__ import annotations

import pytest
from pioreactor.experiment_profiles.sly import Lexer


class CalcLexer(Lexer):
    # Set of token names.   This is always required
    tokens = {
        "ID",
        "NUMBER",
        "PLUS",
        "MINUS",
        "TIMES",
        "DIVIDE",
        "ASSIGN",
        "LT",
        "LE",
    }

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
    LE = r"<="
    LT = r"<"

    @_(r"\d+")
    def NUMBER(self, t):
        t.value = int(t.value)
        return t

    # Ignored text
    ignore_comment = r"\#.*"

    @_(r"\n+")
    def newline(self, t):
        self.lineno += t.value.count("\n")

    # Attached rule
    def ID(self, t):
        t.value = t.value.upper()
        return t

    def error(self, t):
        self.errors.append(t.value)
        self.index += 1
        if hasattr(self, "return_error"):
            return t

    def __init__(self) -> None:
        self.errors = []


# Test basic recognition of various tokens and literals
def test_tokens() -> None:
    lexer = CalcLexer()
    toks = list(lexer.tokenize("abc 123 + - * / = < <= ( )"))
    types = [t.type for t in toks]
    vals = [t.value for t in toks]
    assert types == ["ID", "NUMBER", "PLUS", "MINUS", "TIMES", "DIVIDE", "ASSIGN", "LT", "LE", "(", ")"]
    assert vals == ["ABC", 123, "+", "-", "*", "/", "=", "<", "<=", "(", ")"]


# Test position tracking
def test_positions() -> None:
    lexer = CalcLexer()
    text = "abc\n( )"
    toks = list(lexer.tokenize(text))
    lines = [t.lineno for t in toks]
    indices = [t.index for t in toks]
    ends = [t.end for t in toks]
    values = [text[t.index : t.end] for t in toks]
    assert values == ["abc", "(", ")"]
    assert lines == [1, 2, 2]
    assert indices == [0, 4, 6]
    assert ends == [3, 5, 7]


# Test ignored comments and newlines
def test_ignored() -> None:
    lexer = CalcLexer()
    toks = list(lexer.tokenize("\n\n# A comment\n123\nabc\n"))
    types = [t.type for t in toks]
    vals = [t.value for t in toks]
    linenos = [t.lineno for t in toks]
    assert types == ["NUMBER", "ID"]
    assert vals == [123, "ABC"]
    assert linenos == [4, 5]
    assert lexer.lineno == 6


# Test error handling
def test_error() -> None:
    lexer = CalcLexer()
    toks = list(lexer.tokenize("123 :+-"))
    types = [t.type for t in toks]
    vals = [t.value for t in toks]
    assert types == ["NUMBER", "PLUS", "MINUS"]
    assert vals == [123, "+", "-"]
    assert lexer.errors == [":+-"]


# Test error token return handling
def test_error_return() -> None:
    lexer = CalcLexer()
    lexer.return_error = True
    toks = list(lexer.tokenize("123 :+-"))
    types = [t.type for t in toks]
    vals = [t.value for t in toks]
    assert types == ["NUMBER", "ERROR", "PLUS", "MINUS"]
    assert vals == [123, ":+-", "+", "-"]
    assert lexer.errors == [":+-"]


class ModernCalcLexer(Lexer):
    # Set of token names.   This is always required
    tokens = {ID, NUMBER, PLUS, MINUS, TIMES, DIVIDE, ASSIGN, LT, LE, IF, ELSE}
    literals = {"(", ")"}

    # String containing ignored characters between tokens
    ignore = " \t"

    # Regular expression rules for tokens
    ID = r"[a-zA-Z_][a-zA-Z0-9_]*"
    ID["if"] = IF
    ID["else"] = ELSE

    NUMBER = r"\d+"
    PLUS = r"\+"
    MINUS = r"-"
    TIMES = r"\*"
    DIVIDE = r"/"
    ASSIGN = r"="
    LE = r"<="
    LT = r"<"

    def NUMBER(self, t):
        t.value = int(t.value)
        return t

    # Ignored text
    ignore_comment = r"\#.*"

    @_(r"\n+")
    def ignore_newline(self, t):
        self.lineno += t.value.count("\n")

    # Attached rule
    def ID(self, t):
        t.value = t.value.upper()
        return t

    def error(self, t):
        self.errors.append(t.value)
        self.index += 1
        if hasattr(self, "return_error"):
            return t

    def __init__(self) -> None:
        self.errors = []


# Test basic recognition of various tokens and literals
def test_modern_tokens() -> None:
    lexer = ModernCalcLexer()
    toks = list(lexer.tokenize("abc if else 123 + - * / = < <= ( )"))
    types = [t.type for t in toks]
    vals = [t.value for t in toks]
    assert types == [
        "ID",
        "IF",
        "ELSE",
        "NUMBER",
        "PLUS",
        "MINUS",
        "TIMES",
        "DIVIDE",
        "ASSIGN",
        "LT",
        "LE",
        "(",
        ")",
    ]
    assert vals == ["ABC", "if", "else", 123, "+", "-", "*", "/", "=", "<", "<=", "(", ")"]


# Test ignored comments and newlines
def test_modern_ignored() -> None:
    lexer = ModernCalcLexer()
    toks = list(lexer.tokenize("\n\n# A comment\n123\nabc\n"))
    types = [t.type for t in toks]
    vals = [t.value for t in toks]
    linenos = [t.lineno for t in toks]
    assert types == ["NUMBER", "ID"]
    assert vals == [123, "ABC"]
    assert linenos == [4, 5]
    assert lexer.lineno == 6


# Test error handling
def test_modern_error() -> None:
    lexer = ModernCalcLexer()
    toks = list(lexer.tokenize("123 :+-"))
    types = [t.type for t in toks]
    vals = [t.value for t in toks]
    assert types == ["NUMBER", "PLUS", "MINUS"]
    assert vals == [123, "+", "-"]
    assert lexer.errors == [":+-"]


# Test error token return handling
def test_modern_error_return() -> None:
    lexer = ModernCalcLexer()
    lexer.return_error = True
    toks = list(lexer.tokenize("123 :+-"))
    types = [t.type for t in toks]
    vals = [t.value for t in toks]
    assert types == ["NUMBER", "ERROR", "PLUS", "MINUS"]
    assert vals == [123, ":+-", "+", "-"]
    assert lexer.errors == [":+-"]
