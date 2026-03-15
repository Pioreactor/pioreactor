from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from typing import Generic
from typing import ParamSpec
from typing import TypeVar

P = ParamSpec("P")
R = TypeVar("R")

class Result(Generic[R]):
    @property
    def id(self) -> str: ...
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

class TaskWrapper(Generic[P, R]):
    func: Callable[P, R]
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Result[R]: ...
    def call_local(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    def map(self, it: Iterable[object]) -> ResultGroup[R]: ...

class TaskLock:
    def is_locked(self) -> bool: ...
    def __call__(self, fn: Callable[P, R]) -> Callable[P, R]: ...

class Huey:
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
