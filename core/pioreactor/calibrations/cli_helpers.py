# -*- coding: utf-8 -*-
from click import echo
from click import style


def green(string: str) -> str:
    return style(string, fg="green")


def info(message: str) -> None:
    echo(style(message, fg="white"))


def action(message: str) -> None:
    echo(style(message, fg="cyan"))


def action_block(lines: list[str]) -> None:
    echo()
    for line in lines:
        action(line)
    echo()


def info_heading(message: str) -> None:
    echo(style(message, fg="white", underline=True, bold=True))


def red(string: str) -> str:
    return style(string, fg="red")
