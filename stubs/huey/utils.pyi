from typing import Any
from typing import NamedTuple

class Error(NamedTuple):
    metadata: dict[str, Any]

class _Skipped: ...

SKIPPED: _Skipped
