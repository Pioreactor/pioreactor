from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Iterator
from pathlib import Path
from typing import overload
from typing import Any
from typing import Generic
from typing import ParamSpec
from typing import Protocol
from typing import TypeVar

P = ParamSpec("P")
R = TypeVar("R")
S = TypeVar("S")

class TaskLike(Protocol):
    id: str

class Result(Generic[R]):
    @property
    def id(self) -> str: ...
    def is_ready(self) -> bool: ...
    def get(
        self,
        blocking: bool = ...,
        timeout: float | None = ...,
        backoff: float = ...,
        max_delay: float = ...,
        revoke_on_timeout: bool = ...,
        preserve: bool = ...,
    ) -> R: ...
    def __call__(
        self,
        blocking: bool = ...,
        timeout: float | None = ...,
        backoff: float = ...,
        max_delay: float = ...,
        revoke_on_timeout: bool = ...,
        preserve: bool = ...,
    ) -> R: ...

class ResultGroup(Generic[R]):
    def get(
        self,
        blocking: bool = ...,
        timeout: float | None = ...,
        backoff: float = ...,
        max_delay: float = ...,
        revoke_on_timeout: bool = ...,
        preserve: bool = ...,
    ) -> list[R]: ...
    def __call__(
        self,
        blocking: bool = ...,
        timeout: float | None = ...,
        backoff: float = ...,
        max_delay: float = ...,
        revoke_on_timeout: bool = ...,
        preserve: bool = ...,
    ) -> list[R]: ...
    def __iter__(self) -> Iterator[Result[R]]: ...
    def __len__(self) -> int: ...

class ChordResult(Generic[R]):
    results: ResultGroup[Any]
    callback: Result[R]
    pipeline_results: ResultGroup[Any] | None
    def get(
        self,
        blocking: bool = ...,
        timeout: float | None = ...,
        backoff: float = ...,
        max_delay: float = ...,
        revoke_on_timeout: bool = ...,
        preserve: bool = ...,
    ) -> R: ...
    def __call__(
        self,
        blocking: bool = ...,
        timeout: float | None = ...,
        backoff: float = ...,
        max_delay: float = ...,
        revoke_on_timeout: bool = ...,
        preserve: bool = ...,
    ) -> R: ...
    def reset(self) -> None: ...

class TaskWrapper(Generic[P, R]):
    func: Callable[P, R]
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Result[R]: ...
    def call_local(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    def map(self, it: Iterable[object]) -> ResultGroup[R]: ...
    def s(self, *args: Any, **kwargs: Any) -> TaskLike: ...

class TaskStorage(Protocol):
    def has_data_for_key(self, key: str) -> bool: ...
    def wait_result(
        self,
        key: str,
        timeout: float | None = ...,
        backoff: float = ...,
        max_delay: float = ...,
    ) -> bool: ...

class TaskLock:
    def is_locked(self) -> bool: ...
    def __call__(self, fn: Callable[P, R]) -> Callable[P, R]: ...

class group:
    tasks: Iterable[TaskLike]
    def __init__(self, tasks: Iterable[TaskLike]) -> None: ...
    def then(self, task: TaskWrapper[..., R] | TaskLike, *args: Any, **kwargs: Any) -> chord[R]: ...
    def error(self, *args: Any, **kwargs: Any) -> group: ...

class chord(Generic[R]):
    tasks: Iterable[TaskLike]
    callback: TaskLike
    def __init__(self, tasks: Iterable[TaskLike], callback: TaskWrapper[..., R] | TaskLike) -> None: ...
    def then(self, task: TaskWrapper[..., S] | TaskLike, *args: Any, **kwargs: Any) -> chord[R]: ...
    def error(self, task: TaskWrapper[..., Any] | TaskLike, *args: Any, **kwargs: Any) -> chord[R]: ...

class Huey:
    storage: TaskStorage
    def task(
        self,
        retries: int = ...,
        retry_delay: int = ...,
        priority: int | None = ...,
        context: bool = ...,
        name: str | None = ...,
        expires: Any = ...,
        **kwargs: Any,
    ) -> Callable[[Callable[P, R]], TaskWrapper[P, R]]: ...
    def on_startup(self, name: str | None = ...) -> Callable[[Callable[P, R]], Callable[P, R]]: ...
    def lock_task(self, lock_name: str) -> TaskLock: ...
    @overload
    def enqueue(self, task: chord[R]) -> ChordResult[R]: ...
    @overload
    def enqueue(self, task: group) -> ResultGroup[Any]: ...
    @overload
    def enqueue(self, task: TaskLike) -> Result[Any]: ...
    def result(
        self,
        id: str,
        blocking: bool = ...,
        timeout: float | None = ...,
        backoff: float = ...,
        max_delay: float = ...,
        revoke_on_timeout: bool = ...,
        preserve: bool = ...,
    ) -> Any: ...

class SqliteHuey(Huey):
    def __init__(
        self,
        name: str = ...,
        results: bool = ...,
        store_none: bool = ...,
        utc: bool = ...,
        immediate: bool = ...,
        serializer: Any = ...,
        compression: bool = ...,
        use_zlib: bool = ...,
        immediate_use_memory: bool = ...,
        always_eager: Any = ...,
        storage_class: type[Any] | None = ...,
        filename: str | Path = ...,
        fsync: bool = ...,
        journal_mode: str = ...,
        cache_mb: int = ...,
        timeout: int = ...,
        strict_fifo: bool = ...,
        **storage_kwargs: Any,
    ) -> None: ...
