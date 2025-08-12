# -*- coding: utf-8 -*-
# streaming.py
from __future__ import annotations

import heapq
import io
from queue import Empty
from queue import Queue
from threading import Event
from threading import Thread
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Iterator
from typing import Protocol

from msgspec import DecodeError
from msgspec.json import decode
from pioreactor import types as pt
from pioreactor.pubsub import subscribe
from pioreactor.structs import DosingEvent
from pioreactor.structs import ODReadings
from pioreactor.structs import RawODReading
from pioreactor.utils.timing import to_datetime


class ODObservationSource(Protocol):
    """Anything that can be iterated to yield ODReadings objects."""

    is_live: bool

    def __iter__(self) -> Iterator[ODReadings]:
        ...

    def set_stop_event(self, ev: Event) -> None:
        ...


class DosingObservationSource(Protocol):
    """Anything that can be iterated to yield ODReadings objects."""

    is_live: bool

    def __iter__(self) -> Iterator[DosingEvent]:
        ...

    def set_stop_event(self, ev: Event) -> None:
        ...


class ExportODSource(ODObservationSource):
    is_live = False

    def __init__(
        self,
        filename: str,
        skip_first: int = 0,
        pioreactor_unit: pt.Unit = "$broadcast",
        experiment: pt.Experiment = "$experiment",
    ) -> None:
        self.filename = filename
        self.skip_first = skip_first
        self.pioreactor_unit = pioreactor_unit
        self.experiment = experiment

    def set_stop_event(self, ev: Event) -> None:
        raise NotImplementedError("Does not support live streaming.")

    def __enter__(self, *args, **kwargs):
        import csv

        self.file_instance = open(self.filename, "r")
        self.csv_reader = csv.DictReader(self.file_instance, quoting=csv.QUOTE_MINIMAL)
        return self

    def __exit__(self, *args, **kwargs):
        self.file_instance.close()

    def __iter__(self):
        for i, line in enumerate(self.csv_reader, start=1):
            if i <= self.skip_first:
                continue
            if self.pioreactor_unit != "$broadcast" and self.pioreactor_unit != line["pioreactor_unit"]:
                continue
            if self.experiment != "$experiment" and self.experiment != line["experiment"]:
                continue
            dt = to_datetime(line["timestamp"])
            od = RawODReading(
                angle=line["angle"],
                channel=line["channel"],
                timestamp=dt,
                od=float(line["od_reading"]),
                ir_led_intensity=80,
            )
            ods = ODReadings(timestamp=dt, ods={"2": od})
            yield ods


class EmptyDosingSource(DosingObservationSource):
    """An empty source that yields no dosing events."""

    is_live = True
    _stop_event = Event()

    def __iter__(self) -> Iterator[DosingEvent]:
        return iter([])

    def set_stop_event(self, ev: Event) -> None:
        self._stop_event = ev


class ExportDosingSource(DosingObservationSource):
    is_live = False

    def __init__(
        self,
        filename: str | None,
        skip_first: int = 0,
        pioreactor_unit: pt.Unit = "$broadcast",
        experiment: pt.Experiment = "$experiment",
    ) -> None:
        self.filename = filename
        self.skip_first = skip_first
        self.experiment = experiment
        self.pioreactor_unit = pioreactor_unit

    def set_stop_event(self, ev: Event) -> None:
        raise NotImplementedError("ExportDosingSource does not support live streaming.")

    def __enter__(self, *args, **kwargs):
        import csv

        if self.filename is None:
            # No file?  Give the reader an **empty CSV with headers only**.
            # This satisfies csv.DictReader and still closes cleanly later.
            headers = "timestamp,volume_change_ml,event," "source_of_event,pioreactor_unit,experiment\n"
            self.file_instance = io.StringIO(headers)
        else:
            self.file_instance = open(self.filename, "r")
        self.csv_reader = csv.DictReader(self.file_instance, quoting=csv.QUOTE_MINIMAL)
        return self

    def __exit__(self, *args, **kwargs):
        self.file_instance.close()

    def __iter__(self):
        for i, line in enumerate(self.csv_reader):
            if i <= self.skip_first:
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


class MqttODSource(ODObservationSource):
    is_live = True

    def __init__(self, unit: pt.Unit, experiment: pt.Experiment, *, skip_first: int = 0) -> None:
        self.unit, self.experiment, self.skip_first = unit, experiment, skip_first

    def set_stop_event(self, ev: Event) -> None:
        self._stop_event = ev

    def __iter__(self):
        counter = 0
        while not self._stop_event.is_set():
            msg = subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/od_reading/ods", allow_retained=False, timeout=1
            )
            if msg is None:
                continue
            counter += 1
            if counter <= self.skip_first:
                continue
            try:
                yield decode(msg.payload, type=ODReadings)
            except DecodeError as e:
                print(f"Failed to decode message: {e}")
                continue


class MqttDosingSource(DosingObservationSource):
    is_live = True

    def __init__(self, unit: pt.Unit, experiment: pt.Experiment) -> None:
        self.unit = unit
        self.experiment = experiment

    def set_stop_event(self, ev: Event) -> None:
        self._stop_event = ev

    def __iter__(self):
        while not self._stop_event.is_set():
            msg = subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/dosing_events", allow_retained=False, timeout=1
            )
            if msg is None:
                continue
            try:
                yield decode(msg.payload, type=DosingEvent)
            except DecodeError as e:
                print(f"Failed to decode message: {e}")
                continue


T = ODReadings | DosingEvent
S = ODObservationSource | DosingObservationSource


def merge_live_streams(
    *iterables: S,
    stop_event: Event | None = None,
    poll_interval: float = 0.5,  # seconds to wait before re-checking the flag
    **kwargs,
) -> Iterator[T]:
    """
    Yield the next value that shows up in *any* iterable, but stop as soon as
    `stop_event.set()` is called (or when every iterable is exhausted).
    """
    stop_event = stop_event or Event()
    q: Queue = Queue()

    def _drain(it: S) -> None:
        for item in it:
            if stop_event.is_set():
                break
            q.put(item)

    for it in iterables:
        it.set_stop_event(stop_event)
        Thread(target=_drain, args=(iter(it),), daemon=True).start()

    while True:
        # leave promptly if someone called stop_event.set()
        if stop_event.is_set():
            break
        try:
            item = q.get(timeout=poll_interval)
        except Empty:  # nothing yet → loop back & re-check flag
            continue
        else:
            yield item


def merge_historical_streams(
    *iterables: Iterable[T], key: Callable[[T], Any] = lambda x: x, **kwargs
) -> Iterator[T]:
    """
    Yield items from multiple pre‑sorted streams in ascending order
    according to `key(item)`.

    Parameters
    ----------
    *iterables : Iterable[T]
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
    iters = [iter(s) for s in iterables]

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
