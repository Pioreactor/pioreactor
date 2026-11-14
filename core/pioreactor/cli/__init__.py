# -*- coding: utf-8 -*-
import gc


def main() -> None:
    """
    Entry point of the `pio` console script.

    Starting `pio` creates tens of thousands of long-lived objects (modules, classes, click commands,
    plugins), and the garbage collector repeatedly scans them while collecting nothing. Collection
    is paused here and resumed by `resume_garbage_collection` once the command is about to run.
    """
    gc.disable()
    from pioreactor.cli.pio import pio

    pio()


def resume_garbage_collection() -> None:
    if not gc.isenabled():
        # freeze what startup created, so collections in long-running jobs skip it too.
        gc.freeze()
        gc.enable()
