from typing import Any

class I2C:
    def __init__(self, scl: Any, sda: Any, *, frequency: int = ...) -> None: ...
    def writeto(self, address: int, buffer: bytes | bytearray, *, stop: bool = ...) -> None: ...
    def writeto_then_readfrom(
        self,
        address: int,
        out_buffer: bytes | bytearray,
        in_buffer: bytearray,
        *,
        out_start: int = ...,
        out_end: int | None = ...,
        in_start: int = ...,
        in_end: int | None = ...,
        stop: bool = ...,
    ) -> None: ...
