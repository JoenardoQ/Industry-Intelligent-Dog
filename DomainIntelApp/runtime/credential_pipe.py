"""One-use length-prefixed credential transport; never persists its payload."""

from __future__ import annotations

import json
import struct
from typing import BinaryIO


MAX_CREDENTIAL_BYTES = 64 * 1024


def encode_credential_frame(value: dict | None) -> bytearray:
    payload = bytearray(json.dumps(
        value or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if len(payload) > MAX_CREDENTIAL_BYTES:
        payload[:] = b"\0" * len(payload)
        raise ValueError("credential payload exceeds 64 KiB")
    frame = bytearray(struct.pack(">I", len(payload)))
    frame.extend(payload)
    payload[:] = b"\0" * len(payload)
    return frame


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        value = stream.read(size - len(chunks))
        if not value:
            raise EOFError("credential pipe closed before the frame completed")
        chunks.extend(value)
    result = bytes(chunks)
    chunks[:] = b"\0" * len(chunks)
    return result


def read_credential_frame(stream: BinaryIO, *, allow_eof: bool = False) -> dict:
    header = stream.read(4)
    if not header and allow_eof:
        return {}
    if len(header) != 4:
        raise EOFError("credential pipe header is incomplete")
    length = struct.unpack(">I", header)[0]
    if length > MAX_CREDENTIAL_BYTES:
        raise ValueError("credential payload exceeds 64 KiB")
    raw = bytearray(_read_exact(stream, length))
    try:
        value = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(value, dict):
            raise ValueError("credential payload must be an object")
        return value
    finally:
        raw[:] = b"\0" * len(raw)


def write_credential_frame(stream: BinaryIO, value: dict | None) -> None:
    frame = encode_credential_frame(value)
    try:
        stream.write(frame)
        stream.flush()
    finally:
        frame[:] = b"\0" * len(frame)
        stream.close()
