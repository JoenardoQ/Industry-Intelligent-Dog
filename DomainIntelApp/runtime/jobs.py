"""Persistent subprocess jobs shared by the desktop UI and scheduler."""

from __future__ import annotations

import codecs
import hashlib
import heapq
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


PARTIAL_EXIT_CODE = 4
JOB_LOG_BYTE_CAP = 1_048_576
JOB_LOG_READ_BYTE_CAP = JOB_LOG_BYTE_CAP
JOB_PREVIEW_BYTE_CAP = 16_384
JOB_MANIFEST_BYTE_CAP = 262_144
JOB_LIST_LIMIT = 500
JOB_LEGACY_MANIFEST_BYTE_CAP = JOB_LOG_READ_BYTE_CAP + JOB_MANIFEST_BYTE_CAP
JOB_OUTPUT_READ_CHUNK_BYTES = 8_192
JOB_OUTPUT_QUEUE_MAX_CHUNKS = 8
JOB_OUTPUT_QUEUE_MAX_BYTES = JOB_OUTPUT_READ_CHUNK_BYTES * JOB_OUTPUT_QUEUE_MAX_CHUNKS
JOB_OUTPUT_APPEND_CHAR_CAP = JOB_OUTPUT_READ_CHUNK_BYTES
TASK_LEASE_TTL_SECONDS = 30
JOB_OUTPUT_TRUNCATION_NOTICE = "[可审计输出已达到 1 MiB 上限；后续正文未保存或显示]\n"
JOB_STREAM_SANITIZER_CARRY_CHARS = 256
JOB_STREAM_STRUCTURE_SPACE_REPORT_LIMIT = 64

_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api_key|apikey|access_token|token|key|secret|password)=)"
    r"([^&#\s]+)"
)
_AUTHORIZATION_RE = re.compile(
    r"(?i)(\bAuthorization\s*:\s*(?:Basic|Bearer)\s+)([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\b(Bearer)\s+([^\s,;]+)")
_SK_SECRET_RE = re.compile(r"(?i)\bsk-[A-Za-z0-9._-]+")
_JSON_SECRET_RE = re.compile(
    r'''(?i)(["'](?:api_key|apikey|access_token|token|key|secret|password)'''
    r'''["']\s*:\s*)(?P<quote>["'])(?P<value>(?:\\.|(?!(?P=quote)).)*)(?P=quote)'''
)
_JSON_SCALAR_SECRET_RE = re.compile(
    r'''(?i)(?P<prefix>(?P<keyquote>["'])'''
    r'''(?:api_key|apikey|access_token|token|key|secret|password)'''
    r'''(?P=keyquote)\s*:\s*)'''
    r'''(?P<value>(?!["'])[^\s,}\]]+)'''
)
_ASSIGNED_SECRET_RE = re.compile(
    r"(?ix)\b(api[\s_-]*key|apikey|access[\s_-]*token|token|secret|password)"
    r"(\s*(?:=|:)\s*)([^\s,&;]+)"
)
_PHRASE_SECRET_RE = re.compile(
    r"(?ix)\b(api[\s_-]*key|apikey|access[\s_-]*token|token|secret|password)"
    r"(\s+)([^\s,&;]+)"
)
_SECRET_FLAGS = {
    "--api-key", "--apikey", "--token", "--access-token", "--secret", "--password",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize_text(value: object) -> str:
    """Redact credential-shaped text before persistence or UI exposure."""

    text = str(value)
    text = _QUERY_SECRET_RE.sub(lambda match: f"{match.group(1)}***", text)
    text = _JSON_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{match.group('quote')}***{match.group('quote')}",
        text,
    )
    text = _JSON_SCALAR_SECRET_RE.sub(
        lambda match: f'{match.group("prefix")}"***"',
        text,
    )
    text = _AUTHORIZATION_RE.sub(lambda match: f"{match.group(1)}***", text)
    text = _BEARER_RE.sub(lambda match: f"{match.group(1)} ***", text)
    text = _SK_SECRET_RE.sub("***", text)
    text = _ASSIGNED_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}***", text,
    )

    def redact_credential_phrase(match: re.Match[str]) -> str:
        candidate = match.group(3)
        credential_shaped = len(candidate) >= 8 and (
            any(not character.isalpha() for character in candidate)
            or "secret" in candidate.casefold()
        )
        if not credential_shaped:
            return match.group(0)
        return f"{match.group(1)}{match.group(2)}***"

    text = _PHRASE_SECRET_RE.sub(redact_credential_phrase, text)
    return text


class StreamingSanitizer:
    """Fail-closed bounded state machine for streamed structured credentials."""

    _AUTH_START_RE = re.compile(r"(?i)(?<!\w)Authorization(?!\w)")
    _BEARER_START_RE = re.compile(r"(?i)(?<!\w)Bearer(?!\w)")
    _JSON_KEY_RE = re.compile(
        r'''(?i)(?P<quote>["'])(?:api_key|apikey|access_token|token|key|secret|password)'''
        r'''(?P=quote)'''
    )
    _QUERY_KEY_RE = re.compile(
        r"(?i)[?&](?:api_key|apikey|access_token|token|key|secret|password)(?!\w)"
    )
    _FLAG_RE = re.compile(
        r"(?i)(?<![\w-])--(?:api-key|apikey|access-token|token|secret|password)"
        r"(?![\w-])"
    )
    _SK_START_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])sk-")

    def __init__(self) -> None:
        self._buffer = ""
        self._state = "PLAIN"
        self._json_quote = ""
        self._json_escape = False
        self._auth_scheme = ""
        self._auth_scheme_overflow = False
        self._space_count = 0
        self._space_limit_recorded = False
        self.over_limit_events = 0

    @classmethod
    def _prefix_match(cls, value: str, *, final: bool):
        matches = []
        for priority, (mode, pattern) in enumerate((
            ("AUTH", cls._AUTH_START_RE),
            ("JSON", cls._JSON_KEY_RE),
            ("QUERY", cls._QUERY_KEY_RE),
            ("FLAG", cls._FLAG_RE),
            ("SK", cls._SK_START_RE),
            ("BEARER", cls._BEARER_START_RE),
        )):
            match = pattern.search(value)
            if match is not None and (final or match.end() < len(value)):
                matches.append((match.start(), priority, mode, match))
        return min(matches, default=None, key=lambda item: item[:2])

    def _reset_wait_count(self) -> None:
        self._space_count = 0
        self._space_limit_recorded = False

    def _consume_wait_space(self, output: list[str]) -> bool:
        length = 0
        while length < len(self._buffer) and self._buffer[length].isspace():
            length += 1
        if not length:
            return False
        output.append(self._buffer[:length])
        self._buffer = self._buffer[length:]
        self._space_count = min(
            JOB_STREAM_STRUCTURE_SPACE_REPORT_LIMIT + 1,
            self._space_count + length,
        )
        if (self._space_count > JOB_STREAM_STRUCTURE_SPACE_REPORT_LIMIT
                and not self._space_limit_recorded):
            self._space_limit_recorded = True
            self.over_limit_events = min(self.over_limit_events + 1, 2_147_483_647)
        return True

    def _consume_redaction(self, output: list[str]) -> bool:
        if self._state == "JSON_STRING":
            for index, character in enumerate(self._buffer):
                if self._json_escape:
                    self._json_escape = False
                elif character == "\\":
                    self._json_escape = True
                elif character == self._json_quote:
                    output.append(character)
                    self._buffer = self._buffer[index + 1:]
                    self._state = "PLAIN"
                    self._json_quote = ""
                    return True
            self._buffer = ""
            return False

        if self._state == "REDACT_SK":
            terminates = lambda character: not (
                character.isascii() and (character.isalnum() or character in "._-")
            )
        elif self._state == "REDACT_QUERY":
            terminates = lambda character: character in "&#" or character.isspace()
        elif self._state == "JSON_PRIMITIVE":
            terminates = lambda character: character in ",}]" or character.isspace()
        elif self._state == "LINE_REDACT":
            terminates = lambda character: character in "\r\n"
        else:
            terminates = lambda character: character in ",;" or character.isspace()
        for index, character in enumerate(self._buffer):
            if terminates(character):
                output.append(character)
                self._buffer = self._buffer[index + 1:]
                self._state = "PLAIN"
                return True
        self._buffer = ""
        return False

    def _consume_state(self, output: list[str]) -> bool:
        if self._state in {
            "REDACT_TOKEN", "REDACT_QUERY", "REDACT_SK",
            "JSON_STRING", "JSON_PRIMITIVE", "LINE_REDACT",
        }:
            return self._consume_redaction(output)

        if self._state in {
            "AUTH_COLON", "AUTH_SCHEME_WAIT", "WAIT_TOKEN", "FLAG_SEPARATOR",
            "JSON_COLON", "JSON_VALUE", "QUERY_EQUALS", "QUERY_VALUE",
        }:
            self._consume_wait_space(output)
            if not self._buffer:
                return False

        character = self._buffer[0]
        if self._state == "AUTH_COLON":
            if character == ":":
                output.append(character)
                self._buffer = self._buffer[1:]
                self._state = "AUTH_SCHEME_WAIT"
                self._reset_wait_count()
            else:
                output.append("***")
                self._state = "LINE_REDACT"
            return True

        if self._state == "AUTH_SCHEME_WAIT":
            self._state = "AUTH_SCHEME"
            self._auth_scheme = ""
            self._auth_scheme_overflow = False
            return True

        if self._state == "AUTH_SCHEME":
            length = 0
            while length < len(self._buffer) and self._buffer[length].isalpha():
                if len(self._auth_scheme) < 7:
                    self._auth_scheme += self._buffer[length]
                else:
                    self._auth_scheme_overflow = True
                length += 1
            self._buffer = self._buffer[length:]
            if not self._buffer:
                return False
            if (not self._auth_scheme_overflow
                    and self._auth_scheme.casefold() in {"basic", "bearer"}
                    and self._buffer[0].isspace()):
                output.append(self._auth_scheme)
                self._auth_scheme = ""
                self._state = "WAIT_TOKEN"
                self._reset_wait_count()
            else:
                output.append("***")
                self._auth_scheme = ""
                self._state = "LINE_REDACT"
            return True

        if self._state == "FLAG_SEPARATOR":
            if character == "=":
                output.append(character)
                self._buffer = self._buffer[1:]
            self._state = "WAIT_TOKEN"
            self._reset_wait_count()
            return True

        if self._state == "WAIT_TOKEN":
            output.append("***")
            self._state = "REDACT_TOKEN"
            return True

        if self._state == "JSON_COLON":
            if character == ":":
                output.append(character)
                self._buffer = self._buffer[1:]
                self._state = "JSON_VALUE"
                self._reset_wait_count()
            else:
                output.append("***")
                self._state = "JSON_PRIMITIVE"
            return True

        if self._state == "JSON_VALUE":
            output.append("***")
            if character in {'"', "'"}:
                output.insert(len(output) - 1, character)
                self._buffer = self._buffer[1:]
                self._json_quote = character
                self._json_escape = False
                self._state = "JSON_STRING"
            else:
                self._state = "JSON_PRIMITIVE"
            return True

        if self._state == "QUERY_EQUALS":
            if character == "=":
                output.append(character)
                self._buffer = self._buffer[1:]
                self._state = "QUERY_VALUE"
                self._reset_wait_count()
            else:
                output.append("***")
                self._state = "REDACT_QUERY"
            return True

        if self._state == "QUERY_VALUE":
            output.append("***")
            self._state = "REDACT_QUERY"
            return True

        raise AssertionError(f"unknown streaming sanitizer state: {self._state}")

    def _feed_piece(self, value: str, *, final: bool) -> str:
        self._buffer += value
        output: list[str] = []
        while self._buffer:
            if self._state != "PLAIN":
                if not self._consume_state(output):
                    break
                continue
            found = self._prefix_match(self._buffer, final=final)
            if found is not None:
                start, _priority, mode, match = found
                if start:
                    output.append(sanitize_text(self._buffer[:start]))
                prefix = match.group(0)
                output.append("***" if mode == "SK" else prefix)
                self._buffer = self._buffer[match.end():]
                self._state = {
                    "AUTH": "AUTH_COLON",
                    "BEARER": "WAIT_TOKEN",
                    "FLAG": "FLAG_SEPARATOR",
                    "JSON": "JSON_COLON",
                    "QUERY": "QUERY_EQUALS",
                    "SK": "REDACT_SK",
                }[mode]
                self._reset_wait_count()
                continue
            if final:
                output.append(sanitize_text(self._buffer))
                self._buffer = ""
            else:
                newline = self._buffer.rfind("\n")
                complete_lines = self._buffer[:newline + 1]
                if newline >= 0:
                    output.append(sanitize_text(complete_lines))
                    self._buffer = self._buffer[newline + 1:]
                    continue
            if not final and len(self._buffer) > JOB_STREAM_SANITIZER_CARRY_CHARS:
                safe_length = len(self._buffer) - JOB_STREAM_SANITIZER_CARRY_CHARS
                output.append(sanitize_text(self._buffer[:safe_length]))
                self._buffer = self._buffer[safe_length:]
            break
        return "".join(output)

    def feed(self, value: str) -> str:
        output = []
        for start in range(0, len(value), JOB_OUTPUT_APPEND_CHAR_CAP):
            output.append(self._feed_piece(
                value[start:start + JOB_OUTPUT_APPEND_CHAR_CAP], final=False,
            ))
        return "".join(output)

    def finalize(self) -> str:
        output = self._feed_piece("", final=True)
        if self._state == "AUTH_SCHEME" and self._auth_scheme:
            valid = (
                not self._auth_scheme_overflow
                and self._auth_scheme.casefold() in {"basic", "bearer"}
            )
            output += self._auth_scheme if valid else "***"
        self._state = "PLAIN"
        self._buffer = ""
        self._json_quote = ""
        self._json_escape = False
        self._auth_scheme = ""
        self._auth_scheme_overflow = False
        return output


def sanitize_command(command: list[object]) -> list[str]:
    sanitized: list[str] = []
    redact_next = False
    for part in command:
        text = str(part)
        if redact_next:
            sanitized.append("***")
            redact_next = False
            continue
        sanitized.append(sanitize_text(text))
        redact_next = text.casefold() in _SECRET_FLAGS
    return sanitized


def _output_tail_lines(value: object) -> list[str]:
    if isinstance(value, str):
        return value.splitlines()
    if isinstance(value, (list, tuple)):
        return [str(line) for line in value]
    return []


def _sanitize_manifest(payload: dict) -> dict:
    clean = {key: value for key, value in payload.items() if not str(key).startswith("_")}
    clean["command"] = sanitize_command(list(clean.get("command") or []))
    for field in ("title", "error"):
        if field in clean:
            clean[field] = sanitize_text(clean[field])
    if "output_tail" in clean:
        clean["output_tail"] = [
            sanitize_text(line) for line in _output_tail_lines(clean["output_tail"])
        ]
    if "output" in clean:
        clean["output"] = sanitize_text(clean["output"])
    def sanitize_structure(value: object, key: str = "") -> object:
        if re.search(
                r"(?i)(api[_ -]?key|access[_ -]?token|authorization|password|secret|credential)$",
                key):
            return "***"
        if isinstance(value, dict):
            return {str(item_key): sanitize_structure(item, str(item_key))
                    for item_key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [sanitize_structure(item) for item in value]
        return sanitize_text(value) if isinstance(value, str) else value
    for field in ("operation_payload", "time_window"):
        if field in clean:
            clean[field] = sanitize_structure(clean[field])
    return clean


@dataclass(frozen=True)
class JobResult:
    run_id: str
    status: str
    returncode: int | None
    output: str
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"


class JobStore:
    def __init__(self, data_root: str | Path):
        self.root = Path(data_root) / "_jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.last_list_metadata = {
            "total": 0, "returned": 0, "window_limited": False,
            "read_limited": 0, "selection_bound": JOB_LIST_LIMIT,
        }

    def write(self, payload: dict) -> Path:
        clean = _sanitize_manifest(payload)
        path = self.root / f"{clean['run_id']}.json"
        tmp = path.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(path)
        return path

    @staticmethod
    def _read_bounded(path: Path, cap: int) -> tuple[bytes, bool]:
        with path.open("rb") as handle:
            data = handle.read(cap + 1)
        return data[:cap], len(data) > cap

    @staticmethod
    def _mtime_iso(path: Path) -> str:
        try:
            stamp = path.stat().st_mtime
        except OSError:
            stamp = 0.0
        return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")

    def _limited_manifest(self, path: Path, notice: str) -> dict:
        surrogate = hashlib.sha256(os.fsencode(path.name)).hexdigest()
        return {
            "run_id": f"limited-{surrogate}",
            "status": "history_limited",
            "title": "历史记录受限",
            "updated_at": self._mtime_iso(path),
            "_history_limited": True,
            "_history_notice": notice,
            "_manifest_mtime": self._manifest_mtime(path),
        }

    @staticmethod
    def _manifest_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _read_manifest(self, path: Path, *, include_output: bool = False) -> dict:
        cap = JOB_LEGACY_MANIFEST_BYTE_CAP if include_output else JOB_MANIFEST_BYTE_CAP
        try:
            data, limited = self._read_bounded(path, cap)
            if limited:
                return self._limited_manifest(
                    path,
                    f"历史 manifest 读取受限：超过 {cap} 字节上限；文件仍保留，详情不可解析。",
                )
            payload = json.loads(data.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("manifest is not an object")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return self._limited_manifest(
                path, "历史 manifest 不可解析；文件仍保留且未伪装为空记录。",
            )
        payload.setdefault("run_id", path.stem)
        if "output" in payload and not include_output:
            payload.pop("output")
            payload["_legacy_output"] = True
        return _sanitize_manifest(payload) | {
            key: value for key, value in payload.items() if str(key).startswith("_")
        } | {"_manifest_mtime": self._manifest_mtime(path)}

    @staticmethod
    def _timestamp_value(payload: dict) -> float:
        for field in ("updated_at", "finished_at", "started_at", "created_at"):
            value = payload.get(field)
            if not value:
                continue
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError, OverflowError):
                continue
        return float(payload.get("_manifest_mtime") or 0.0)

    def list(self, *, limit: int = JOB_LIST_LIMIT) -> list[dict]:
        bounded_limit = max(0, min(int(limit), JOB_LIST_LIMIT))
        newest: list[tuple[float, int, dict]] = []
        total = 0
        for sequence, path in enumerate(self.root.glob("*.json")):
            payload = self._read_manifest(path)
            total += 1
            if not bounded_limit:
                continue
            entry = (self._timestamp_value(payload), sequence, payload)
            if len(newest) < bounded_limit:
                heapq.heappush(newest, entry)
            elif entry[:2] > newest[0][:2]:
                heapq.heapreplace(newest, entry)
        visible = [
            entry[2] for entry in sorted(newest, key=lambda item: item[:2], reverse=True)
        ]
        self.last_list_metadata = {
            "total": total,
            "returned": len(visible),
            "window_limited": total > len(visible),
            "read_limited": sum(bool(row.get("_history_limited")) for row in visible),
            "selection_bound": bounded_limit,
        }
        return visible

    @staticmethod
    def _valid_run_id(run_id: object) -> str:
        value = str(run_id or "")
        if not value or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
            raise ValueError("Invalid job run_id")
        return value

    def append_output(self, run_id: object, text: object) -> dict[str, object]:
        value = self._valid_run_id(run_id)
        path = self.root / f"{value}.log"
        source = text if isinstance(text, str) else str(text)
        bounded_source = source[:JOB_OUTPUT_APPEND_CHAR_CAP]
        input_limited = len(source) > len(bounded_source)
        encoded = sanitize_text(bounded_source).encode("utf-8")
        with self._lock:
            current = path.stat().st_size if path.exists() else 0
            remaining = max(0, JOB_LOG_BYTE_CAP - current)
            chunk = encoded[:remaining]
            while chunk:
                try:
                    chunk.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    chunk = chunk[:-1]
            if chunk:
                with path.open("ab") as handle:
                    handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
            size = current + len(chunk)
        accepted_text = chunk.decode("utf-8") if chunk else ""
        return {
            "output_log": path.name,
            "output_bytes": size,
            "output_truncated": (
                input_limited or len(encoded) > len(chunk)
                or current >= JOB_LOG_BYTE_CAP
            ),
            "_accepted_text": accepted_text,
        }

    @staticmethod
    def _bounded_legacy_output(value: object) -> str:
        safe = sanitize_text(value)
        raw = safe.encode("utf-8")
        encoded = raw[:JOB_LOG_READ_BYTE_CAP]
        text = encoded.decode("utf-8", errors="ignore")
        if len(raw) > len(encoded):
            text += "\n[历史输出已达到读取上限，后续内容未显示]\n"
        return text

    @staticmethod
    def _merge_legacy_output(output: object, output_tail: object) -> str:
        base = sanitize_text(output or "")
        tail_lines = [
            sanitize_text(line) for line in _output_tail_lines(output_tail)
        ]
        if not tail_lines:
            return base
        base_lines = base.rstrip("\n").split("\n") if base else []
        overlap = 0
        for size in range(min(len(base_lines), len(tail_lines)), 0, -1):
            if base_lines[-size:] == tail_lines[:size]:
                overlap = size
                break
        remainder = tail_lines[overlap:]
        if not remainder:
            return base
        separator = "" if not base or base.endswith("\n") else "\n"
        remainder_text = "\n".join(remainder)
        return f"{base}{separator}{remainder_text}"

    def _replace_migrated_output(self, run_id: object, text: str) -> dict[str, object]:
        value = self._valid_run_id(run_id)
        path = self.root / f"{value}.log"
        tmp = path.with_suffix(".log.migrate.tmp")
        encoded = text.encode("utf-8")
        chunk = encoded[:JOB_LOG_BYTE_CAP]
        while chunk:
            try:
                chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk = chunk[:-1]
        with self._lock:
            try:
                with tmp.open("wb") as handle:
                    handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
            finally:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
        return {
            "output_log": path.name,
            "output_bytes": len(chunk),
            "output_truncated": len(encoded) > len(chunk),
        }

    def read_output(self, payload: dict) -> str:
        if payload.get("_history_limited"):
            return sanitize_text(
                payload.get("_history_notice") or "历史详情读取受限。"
            )
        run_id = self._valid_run_id(payload.get("run_id"))
        sidecar = self.root / f"{run_id}.log"
        truncated = bool(payload.get("output_truncated"))
        if sidecar.exists():
            try:
                if sidecar.stat().st_size >= JOB_LOG_BYTE_CAP:
                    truncated = True
                with sidecar.open("rb") as handle:
                    data = handle.read(JOB_LOG_READ_BYTE_CAP + 1)
            except OSError:
                data = b""
            if len(data) > JOB_LOG_READ_BYTE_CAP:
                data = data[:JOB_LOG_READ_BYTE_CAP]
                truncated = True
            text = data.decode("utf-8", errors="replace")
            if truncated:
                text += "\n[日志已达到读取上限，后续输出未保存]\n"
            return sanitize_text(text)
        if "output" in payload:
            return self._bounded_legacy_output(self._merge_legacy_output(
                payload.get("output"), payload.get("output_tail"),
            ))
        if payload.get("_legacy_output"):
            legacy = self._read_manifest(
                self.root / f"{run_id}.json", include_output=True,
            )
            if legacy.get("_history_limited"):
                return sanitize_text(legacy.get("_history_notice") or "历史详情读取受限。")
            return self._bounded_legacy_output(self._merge_legacy_output(
                legacy.get("output"), legacy.get("output_tail"),
            ))
        return "\n".join(
            sanitize_text(line) for line in _output_tail_lines(payload.get("output_tail"))
        )

    def recover_interrupted(self) -> int:
        recovered = 0
        for path in self.root.glob("*.json"):
            payload = self._read_manifest(path, include_output=True)
            if payload.get("_history_limited"):
                continue
            if payload.get("status") not in {"queued", "running", "cancelling"}:
                continue
            owner_pid = payload.get("owner_pid")
            if owner_pid and self._pid_alive(owner_pid):
                continue
            if "output" in payload:
                legacy_output = payload.pop("output")
                migrated_output = self._merge_legacy_output(
                    legacy_output, payload.get("output_tail"),
                )
                metadata = self._replace_migrated_output(
                    payload.get("run_id"), migrated_output,
                )
                preview = migrated_output.encode("utf-8")[-JOB_PREVIEW_BYTE_CAP:]
                payload["output_tail"] = preview.decode(
                    "utf-8", errors="ignore",
                ).split("\n")
                payload.update(metadata)
                payload["legacy_output_migrated"] = True
                payload["legacy_output_truncated"] = bool(
                    metadata.get("output_truncated")
                )
            sidecar = self.root / f"{self._valid_run_id(payload.get('run_id'))}.log"
            try:
                sidecar_size = sidecar.stat().st_size
            except OSError:
                sidecar_size = 0
            if sidecar_size >= JOB_LOG_BYTE_CAP:
                payload["output_truncated"] = True
                payload["output_bytes"] = min(sidecar_size, JOB_LOG_BYTE_CAP)
            payload.update({"status": "interrupted", "finished_at": _now(),
                            "updated_at": _now(),
                            "error": "App session ended before the job reached a terminal state"})
            self.write(payload); recovered += 1
        return recovered

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, TypeError, ValueError):
            return False


class ManagedJob:
    def __init__(self, manager: "JobManager", command: list[str], *, cwd: str | Path,
                 title: str, timeout: float | None = None,
                 on_output: Callable[[str], None] | None = None,
                 on_finish: Callable[[JobResult], None] | None = None,
                 env: dict[str, str] | None = None,
                 metadata: dict | None = None):
        self.manager = manager
        self.command = [str(part) for part in command]
        self.cwd = str(Path(cwd))
        self.title = title
        self.timeout = timeout
        self.on_output = on_output
        self.on_finish = on_finish
        self.env = env
        self.metadata = dict(metadata or {})
        self._ledger_enabled = False
        self.run_id = uuid.uuid4().hex
        ledger = manager.ledger
        operation_payload = self.metadata.get("operation_payload")
        if not isinstance(operation_payload, dict):
            operation_payload = {}
        folder = str(self.metadata.get("folder") or
                     operation_payload.get("folder") or "").strip()
        if ledger is not None and folder:
            task = ledger.create_task(
                folder=folder,
                operation=str(self.metadata.get("operation") or "job"),
                input=operation_payload,
                origin=str(self.metadata.get("origin") or "app"),
                provider=str(self.metadata.get("provider") or
                             operation_payload.get("provider") or "local"),
                model=str(self.metadata.get("model") or
                          operation_payload.get("model") or ""),
                parent_run_id=self.metadata.get("parent_run_id"),
                time_window=self.metadata.get("time_window"),
                output_path=str(self.metadata.get("output_path") or ""),
                credential_handle_ref=self.metadata.get("credential_handle_ref"),
            )
            self.run_id = task["id"]
            self._ledger_enabled = True
        self._cancel = threading.Event()
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._runner_thread: threading.Thread | None = None
        self.result: JobResult | None = None
        self._output_truncation_notified = False
        self._manifest = {
            "run_id": self.run_id, "title": title, "status": "queued",
            "command": sanitize_command(self.command), "cwd": self.cwd,
            "timeout": timeout,
            "owner_pid": os.getpid(), "session_id": manager.session_id,
            "pid": None, "created_at": _now(), "started_at": None,
            "finished_at": None, "updated_at": _now(), "returncode": None,
            "last_heartbeat_at": None, "last_progress_at": None,
            "cancel_requested": False, "error": "", "output_tail": [],
            "output_log": f"{self.run_id}.log", "output_bytes": 0,
            "output_truncated": False,
            "operation": self.metadata.get("operation", ""),
            "operation_payload": self.metadata.get("operation_payload", {}),
            "parent_run_id": self.metadata.get("parent_run_id"),
            "schedule_action": self.metadata.get("schedule_action"),
            "stage": "queued", "progress": 0.0, "artifact_path": None,
        }
        self.manager.store.write(self._manifest)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self) -> "ManagedJob":
        self._thread = threading.Thread(target=self.run, daemon=True,
                                        name=f"intdog-job-{self.run_id[:8]}")
        self._thread.start()
        return self

    def cancel(self) -> bool:
        if self.result is not None:
            return False
        self._cancel.set()
        if self._ledger_enabled:
            try:
                self.manager.ledger.transition(
                    self.run_id, expected={"queued", "running"},
                    target="cancelling",
                    error={"category": "cancel_requested",
                           "message": "Cancelled by user"})
            except (ValueError, RuntimeError):
                pass
        self._manifest.update({"status": "cancelling", "cancel_requested": True,
                               "updated_at": _now()})
        self.manager.store.write(self._manifest)
        self._terminate(force=False)
        return True

    def wait(self, timeout: float | None = None) -> JobResult | None:
        runner = self._runner_thread or self._thread
        if runner is not None and runner is not threading.current_thread():
            runner.join(timeout)
        return self.result

    def _terminate(self, *, force: bool) -> None:
        with self._lock:
            proc = self._process
        if proc is None or proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                args = ["taskkill", "/PID", str(proc.pid), "/T"]
                if force:
                    args.append("/F")
                subprocess.run(args, capture_output=True, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                os.killpg(proc.pid, signal.SIGKILL if force else signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                proc.kill() if force else proc.terminate()
            except OSError:
                pass

    def _save(self, **changes) -> None:
        self._manifest.update(changes)
        self._manifest["updated_at"] = _now()
        self.manager.store.write(self._manifest)
        if self._ledger_enabled and ({"stage", "progress", "last_heartbeat_at"}
                                     & set(changes)):
            status = self.manager.ledger.get_task(self.run_id)["status"]
            if status in {"running", "cancelling"}:
                progress = self._manifest.get("progress", 0)
                percent = int(round(float(progress) * 100)) if float(progress) <= 1 else int(
                    round(float(progress)))
                self.manager.ledger.heartbeat(
                    self.run_id, owner=self.manager.ledger_owner,
                    stage=str(self._manifest.get("stage") or "running"),
                    progress=max(0, min(percent, 100)),
                    checkpoint={
                        "output_bytes": int(self._manifest.get("output_bytes") or 0),
                        "output_truncated": bool(self._manifest.get("output_truncated")),
                    })
        if self._ledger_enabled and changes.get("artifact_path"):
            self.manager.ledger.update_task_output(
                self.run_id, str(changes["artifact_path"]),
                owner=self.manager.ledger_owner)

    def _emit(self, line: str) -> None:
        if self._manifest.get("output_truncated"):
            return
        metadata = self.manager.store.append_output(self.run_id, line)
        safe = str(metadata.pop("_accepted_text", ""))
        preview = "\n".join([
            *self._manifest.setdefault("output_tail", []), safe.rstrip("\n"),
        ])
        encoded = preview.encode("utf-8")
        if len(encoded) > JOB_PREVIEW_BYTE_CAP:
            encoded = encoded[-JOB_PREVIEW_BYTE_CAP:]
            preview = encoded.decode("utf-8", errors="ignore")
        tail = preview.split("\n")
        changes = {"output_tail": tail, "last_progress_at": _now(), **metadata}
        stage = re.search(r"\[阶段\s*(\d+)\s*/\s*(\d+)\]\s*([^\n]*)", safe)
        if stage:
            current, total = int(stage.group(1)), max(1, int(stage.group(2)))
            changes.update({"stage": stage.group(3).strip() or f"阶段 {current}/{total}",
                            "progress": round(current / total, 4)})
        artifact = re.search(
            r"\[完成\](?:[^\n]*?[：:]\s*|\s+)(\S+\.(?:md|json|html|txt))", safe,
        )
        if artifact:
            changes["artifact_path"] = artifact.group(1)
        self._save(**changes)
        if self.on_output and safe:
            self.on_output(safe)
        if metadata.get("output_truncated") and not self._output_truncation_notified:
            self._output_truncation_notified = True
            if self.on_output:
                self.on_output(JOB_OUTPUT_TRUNCATION_NOTICE)

    def run(self) -> JobResult:
        self._runner_thread = threading.current_thread()
        self.manager._register(self)
        started = time.monotonic()
        cancelled_at = None
        output_queue: queue.Queue[bytes | None] = queue.Queue(
            maxsize=JOB_OUTPUT_QUEUE_MAX_CHUNKS,
        )
        try:
            if self._ledger_enabled and not self.manager.ledger.claim_expired(
                    self.run_id, self.manager.ledger_owner,
                    TASK_LEASE_TTL_SECONDS):
                task = self.manager.ledger.get_task(self.run_id)
                status = task["status"]
                error = str(task.get("error", {}).get("message") or
                            "Task could not acquire its authoritative lease")
                result = JobResult(self.run_id, status, None, "", error)
                self.result = result
                self._save(status=status, error=error, finished_at=_now())
                self.manager._finish(self)
                if self.on_finish:
                    self.on_finish(result)
                return result
            flags = 0
            kwargs = {}
            if os.name == "nt":
                flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0) |
                         getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            else:
                kwargs["start_new_session"] = True
            child_env = dict(self.env or os.environ)
            credential_payload: dict = {}
            if self.manager.credential_supplier:
                child_env["INTDOG_CREDENTIAL_PIPE"] = "1"
                operation_payload = self.metadata.get("operation_payload")
                payload_provider = (operation_payload.get("provider")
                                    if isinstance(operation_payload, dict) else "")
                credential_payload = self.manager.credential_supplier(
                    str(self.metadata.get("provider") or
                        payload_provider or "local"),
                    str(self.metadata.get("operation") or "job")) or {}
                if not isinstance(credential_payload, dict):
                    raise TypeError("credential supplier must return an object")
            child_env.setdefault("PYTHONUTF8", "1")
            child_env.setdefault("PYTHONIOENCODING", "utf-8")
            proc = subprocess.Popen(
                self.command, cwd=self.cwd, env=child_env,
                stdin=(subprocess.PIPE if self.manager.credential_supplier
                       else subprocess.DEVNULL),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=flags, **kwargs)
            with self._lock:
                self._process = proc
            if self.manager.credential_supplier:
                from runtime.credential_pipe import write_credential_frame
                try:
                    assert proc.stdin is not None
                    write_credential_frame(
                        proc.stdin, credential_payload)
                except Exception as exc:
                    self._terminate(force=True)
                    raise RuntimeError("credential pipe delivery failed") from exc
                finally:
                    for key in tuple(credential_payload):
                        credential_payload[key] = ""
                    credential_payload.clear()
            self._save(status="running", pid=proc.pid, started_at=_now())
            if self._ledger_enabled:
                self.manager.ledger.mark_request_dispatched(
                    self.run_id, owner=self.manager.ledger_owner)
            last_heartbeat = time.monotonic()

            def read_output():
                assert proc.stdout is not None
                try:
                    while True:
                        if hasattr(proc.stdout, "read1"):
                            chunk = proc.stdout.read1(JOB_OUTPUT_READ_CHUNK_BYTES)
                        else:
                            chunk = proc.stdout.read(JOB_OUTPUT_READ_CHUNK_BYTES)
                        if not chunk:
                            break
                        output_queue.put(chunk)
                finally:
                    output_queue.put(None)

            reader = threading.Thread(target=read_output, daemon=True,
                                      name=f"intdog-reader-{self.run_id[:8]}")
            reader.start(); reader_done = False; timed_out = False
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            redactor = StreamingSanitizer()

            def emit_sanitized(value: str) -> None:
                for offset in range(0, len(value), JOB_OUTPUT_APPEND_CHAR_CAP):
                    self._emit(value[offset:offset + JOB_OUTPUT_APPEND_CHAR_CAP])

            while True:
                try:
                    chunk = output_queue.get(timeout=0.1)
                    if chunk is None:
                        remainder = decoder.decode(b"", final=True)
                        if remainder:
                            emit_sanitized(redactor.feed(remainder))
                        emit_sanitized(redactor.finalize())
                        reader_done = True
                    else:
                        decoded = decoder.decode(chunk)
                        if decoded:
                            emit_sanitized(redactor.feed(decoded))
                except queue.Empty:
                    pass
                if time.monotonic() - last_heartbeat >= 5:
                    self._save(last_heartbeat_at=_now())
                    last_heartbeat = time.monotonic()
                if self._cancel.is_set():
                    if cancelled_at is None:
                        cancelled_at = time.monotonic(); self._terminate(force=False)
                    elif time.monotonic() - cancelled_at >= 2:
                        self._terminate(force=True)
                if (self.timeout is not None and time.monotonic() - started >= self.timeout
                        and proc.poll() is None):
                    timed_out = True; self._cancel.set(); self._terminate(force=True)
                if proc.poll() is not None and reader_done and output_queue.empty():
                    break
            returncode = proc.wait()
            if timed_out:
                status, error = "failed", f"Timeout after {self.timeout:g}s"
            elif self._cancel.is_set():
                status, error = "cancelled", "Cancelled by user"
            elif returncode == 0:
                status, error = "completed", ""
            elif returncode == PARTIAL_EXIT_CODE:
                status, error = "partial", "One or more collection categories failed"
            else:
                status, error = "failed", f"Process exited with {returncode}"
        except Exception as exc:
            lease_lost = isinstance(exc, RuntimeError) and "lease was lost" in str(exc)
            if lease_lost:
                self._terminate(force=True)
            returncode = None
            status = ("interrupted" if lease_lost else
                      "cancelled" if self._cancel.is_set() else "failed")
            error = sanitize_text(f"{type(exc).__name__}: {exc}")
            self._emit(error + "\n")
        finally:
            with self._lock:
                proc = self._process
                self._process = None
            if proc and proc.stdout:
                proc.stdout.close()
        error = sanitize_text(error)
        result = JobResult(
            self.run_id, status, returncode,
            self.manager.store.read_output(self._manifest), error,
        )
        self.result = result
        if self._ledger_enabled:
            current = self.manager.ledger.get_task(self.run_id)["status"]
            try:
                self.manager.ledger.transition(
                    self.run_id, expected={current}, target=status,
                    owner=self.manager.ledger_owner,
                    error=({"category": "process_failure", "message": error}
                           if error else None))
            except RuntimeError as exc:
                if "lease was lost" not in str(exc):
                    raise
        self._save(
            status=status, returncode=returncode, error=error,
            finished_at=_now(),
        )
        self.manager._finish(self)
        if self.on_finish:
            self.on_finish(result)
        return result


class JobManager:
    def __init__(self, data_root: str | Path, *, ledger=None,
                 credential_supplier: Callable[[str, str], dict] | None = None):
        self.store = JobStore(data_root)
        self.session_id = uuid.uuid4().hex
        self.ledger = ledger
        self.credential_supplier = credential_supplier
        self.ledger_owner = f"job-manager:{os.getpid()}:{self.session_id}"
        self._active: dict[str, ManagedJob] = {}
        self._lock = threading.Lock()
        self.recovered = self.store.recover_interrupted()
        self.recovered_ledger = (
            self.ledger.recover_expired_tasks(actor=self.ledger_owner)
            if self.ledger is not None else [])

    def create(self, command: list[str], *, cwd: str | Path, title: str,
               timeout: float | None = None,
               on_output: Callable[[str], None] | None = None,
               on_finish: Callable[[JobResult], None] | None = None,
               env: dict[str, str] | None = None,
               metadata: dict | None = None) -> ManagedJob:
        return ManagedJob(self, command, cwd=cwd, title=title, timeout=timeout,
                          on_output=on_output, on_finish=on_finish, env=env,
                          metadata=metadata)

    def start(self, *args, **kwargs) -> ManagedJob:
        return self.create(*args, **kwargs).start()

    def run_sync(self, *args, **kwargs) -> JobResult:
        return self.create(*args, **kwargs).run()

    def _register(self, job: ManagedJob) -> None:
        with self._lock:
            self._active[job.run_id] = job

    def _finish(self, job: ManagedJob) -> None:
        with self._lock:
            self._active.pop(job.run_id, None)

    def cancel_all(self) -> int:
        with self._lock:
            jobs = list(self._active.values())
        return sum(job.cancel() for job in jobs)

    def shutdown(self, timeout: float = 3.0) -> int:
        with self._lock:
            jobs = list(self._active.values())
        cancelled = sum(job.cancel() for job in jobs)
        deadline = time.monotonic() + max(0.0, timeout)
        for job in jobs:
            job.wait(max(0.0, deadline - time.monotonic()))
        survivors = [job for job in jobs if job.running]
        for job in survivors:
            job._terminate(force=True)
        for job in survivors:
            job.wait(1.0)
        return cancelled

    def active(self) -> list[ManagedJob]:
        with self._lock:
            return list(self._active.values())
