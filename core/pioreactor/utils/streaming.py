# -*- coding: utf-8 -*-
# streaming.py
import heapq
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
from pioreactor.structs import ODFused
from pioreactor.structs import ODReadings
from pioreactor.structs import RawODReading

FUSED_PD_CHANNEL: pt.PdChannel = "1"
FUSED_PD_ANGLE: pt.PdAngle = "90"


class ODObservationSource(Protocol):
    """Anything that can be iterated to yield ODReadings objects."""

    is_live: bool

    def __iter__(self) -> Iterator[ODReadings]: ...

    def set_stop_event(self, ev: Event) -> None: ...


class DosingObservationSource(Protocol):
    """Anything that can be iterated to yield ODReadings objects."""

    is_live: bool

    def __iter__(self) -> Iterator[DosingEvent]: ...

    def set_stop_event(self, ev: Event) -> None: ...


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


class MqttODFusedSource(ODObservationSource):
    is_live = True

    def __init__(self, unit: pt.Unit, experiment: pt.Experiment, *, skip_first: int = 0) -> None:
        self.unit, self.experiment, self.skip_first = unit, experiment, skip_first

    def set_stop_event(self, ev: Event) -> None:
        self._stop_event = ev

    def __iter__(self):
        counter = 0
        while not self._stop_event.is_set():
            msg = subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/od_reading/od_fused",
                allow_retained=False,
                timeout=1,
            )
            if msg is None:
                continue
            counter += 1
            if counter <= self.skip_first:
                continue
            try:
                fused = decode(msg.payload, type=ODFused)
            except DecodeError as e:
                print(f"Failed to decode message: {e}")
                continue

            yield ODReadings(
                timestamp=fused.timestamp,
                ods={
                    FUSED_PD_CHANNEL: RawODReading(
                        timestamp=fused.timestamp,
                        angle=FUSED_PD_ANGLE,
                        od=fused.od_fused,
                        channel=FUSED_PD_CHANNEL,
                        ir_led_intensity=0.0,
                    )
                },
            )


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


def merge_live_streams(
    *iterables: Iterable[T],
    stop_event: Event | None = None,
    poll_interval: float = 0.5,  # seconds to wait before re-checking the flag
) -> Iterator[T]:
    """
    Yield the next value that shows up in *any* iterable, but stop as soon as
    `stop_event.set()` is called (or when every iterable is exhausted).
    """
    stop_event = stop_event or Event()
    q: Queue = Queue()

    def _drain(it: Iterable[T]) -> None:
        for item in it:
            if stop_event.is_set():
                break
            q.put(item)

    for it in iterables:
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


def merge_historical_streams(*iterables: Iterable[T], key: Callable[[T], Any] = lambda x: x) -> Iterator[T]:
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
