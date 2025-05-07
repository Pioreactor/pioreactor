# -*- coding: utf-8 -*-
# utils.py
from __future__ import annotations

import heapq
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Iterator
from typing import TypeVar

from pioreactor.structs import DosingEvent
from pioreactor.structs import ODReadings
from pioreactor.structs import RawODReading
from pioreactor.utils.timing import to_datetime

T = TypeVar("T")


def merge_streams(
    *streams: Iterable[T],
    key: Callable[[T], Any] = lambda x: x,
) -> Iterator[T]:
    """
    Yield items from multiple pre‑sorted streams in ascending order
    according to `key(item)`.

    Parameters
    ----------
    *streams : Iterable[T]
        Any number of iterables / generators whose items are already
        sorted by `key`.
    key : Callable[[T], Any], optional
        Function that returns the sort key for each item.  Defaults to
        the identity function.

    Yields
    ------
    T
        The next smallest item across all input streams.
    """
    # Build an iterator for each stream
    iters = [iter(s) for s in streams]

    # Prime the priority queue with the first element from each stream
    # The queue holds tuples: (sort_key, stream_index, item)
    pq: list[tuple[Any, int, T]] = []
    for idx, it in enumerate(iters):
        try:
            first = next(it)
            heapq.heappush(pq, (key(first), idx, first))
        except StopIteration:
            pass  # this stream was empty

    while pq:
        k, idx, item = heapq.heappop(pq)
        yield item  # hand the smallest out
        try:
            nxt = next(iters[idx])  # fetch the next from that stream
            heapq.heappush(pq, (key(nxt), idx, nxt))
        except StopIteration:
            pass  # that stream exhausted → drop it


class StreamODReadingsFromExport:
    def __init__(
        self,
        filename: str,
        skip_first_n_rows: int = 0,
        pioreactor_unit: str = "$broadcast",
        experiment="$experiment",
    ):
        self.filename = filename
        self.skip_first_n_rows = skip_first_n_rows
        self.pioreactor_unit = pioreactor_unit
        self.experiment = experiment

    def __enter__(self, *args, **kwargs):
        import csv

        self.file_instance = open(self.filename, "r")
        self.csv_reader = csv.DictReader(self.file_instance, quoting=csv.QUOTE_MINIMAL)
        return self

    def __exit__(self, *args, **kwargs):
        self.file_instance.close()

    def __iter__(self):
        for i, line in enumerate(self.csv_reader):
            if i <= self.skip_first_n_rows:
                continue
            if self.pioreactor_unit != "$broadcast" and self.pioreactor_unit != line["pioreactor_unit"]:
                continue
            if self.experiment != "$experiment" and self.experiment != line["experiment"]:
                continue
            dt = to_datetime(line["timestamp"])
            od = RawODReading(
                angle=line["angle"], channel=line["channel"], timestamp=dt, od=float(line["od_reading"])
            )
            ods = ODReadings(timestamp=dt, ods={"2": od})
            yield ods


class StreamDosingEventsFromExport:
    def __init__(
        self,
        filename: str,
        skip_first_n_rows: int = 0,
        pioreactor_unit: str = "$broadcast",
        experiment="$experiment",
    ):
        self.filename = filename
        self.skip_first_n_rows = skip_first_n_rows
        self.experiment = experiment
        self.pioreactor_unit = pioreactor_unit

    def __enter__(self, *args, **kwargs):
        import csv

        self.file_instance = open(self.filename, "r")
        self.csv_reader = csv.DictReader(self.file_instance, quoting=csv.QUOTE_MINIMAL)
        return self

    def __exit__(self, *args, **kwargs):
        self.file_instance.close()

    def __iter__(self):
        for i, line in enumerate(self.csv_reader):
            if i <= self.skip_first_n_rows:
                continue
            if self.pioreactor_unit != "$broadcast" and self.pioreactor_unit != line["pioreactor_unit"]:
                continue
            if self.experiment != "$experiment" and self.experiment != line["experiment"]:
                continue
            dt = to_datetime(line["timestamp"])
            event = DosingEvent(
                volume_change=float(line["volume_change_ml"]),
                timestamp=dt,
                event=line["event"],
                source_of_event=line["source_of_event"],
            )
            yield event
