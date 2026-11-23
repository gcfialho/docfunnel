"""Resolve a document source (local path, http(s) URL or raw bytes) to a local file.

The parse stage works on files, and picks the parser from the file suffix. This module
turns whatever a caller has, often an agent passing a string, into such a file:

* a **local path** is used as is, optionally confined to ``FetchPolicy.base_dir``;
* an **http(s) URL** is downloaded to a temporary file, with a size cap, a timeout and
  a check that every host it resolves to (redirects included) is a public address;
* **bytes** are written to a temporary file.

The suffix comes from the path or URL when it names a supported type, else from the
``Content-Type`` header, else from the file's first bytes (``%PDF``, PNG, JPEG, TIFF,
WebP, BMP, or UTF-8 text).

Downloads are a server-side request made on behalf of the caller, so the defaults are
conservative: private, loopback and link-local addresses are refused. The check runs
on the resolved addresses before each request; it does not pin the connection to them,
so for untrusted input in a sensitive network also set ``allowed_hosts``.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import tempfile
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from docfunnel.parse.pipeline import IMAGE_SUFFIXES, PDF_SUFFIXES, TEXT_SUFFIXES

SourceLike = str | os.PathLike[str] | bytes
"""A local path, an ``http(s)://`` URL, or the document's raw bytes."""

SUPPORTED_SUFFIXES = frozenset(PDF_SUFFIXES | IMAGE_SUFFIXES | TEXT_SUFFIXES)

_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "text/plain": ".txt",
    "text/markdown": ".md",
}
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_CHUNK = 64 * 1024


class SourceError(ValueError):
    """The source cannot be used: not found, not allowed, too large or of an unknown type."""


@dataclass(frozen=True)
class FetchPolicy:
    """What :func:`open_source` may read. The defaults suit a local library call."""

    allow_local_files: bool = True
    base_dir: Path | None = None
    """When set, local paths must resolve inside this directory."""
    allow_urls: bool = True
    allow_private_hosts: bool = False
    """Allow URLs that resolve to private, loopback, link-local or reserved addresses."""
    allowed_hosts: frozenset[str] | None = None
    """When set, only these host names may be fetched (redirect targets included)."""
    max_bytes: int = 50 * 1024 * 1024
    timeout_s: float = 30.0
    max_redirects: int = 5


@dataclass(frozen=True)
class ResolvedSource:
    path: Path
    """A local file with a supported suffix (temporary for URLs and bytes)."""
    name: str
    """A short document id: the file stem, the last URL path segment, or "document"."""
    origin: str
    """The path or URL the caller gave, for reports; ``"<bytes>"`` for raw bytes."""


def is_url(source: object) -> bool:
    return isinstance(source, str) and urlsplit(source).scheme.lower() in {"http", "https"}


@contextmanager
def open_source(
    source: SourceLike, policy: FetchPolicy | None = None, *, name: str | None = None
) -> Iterator[ResolvedSource]:
    """Yield a local file for ``source``; temporary files are removed on exit."""
    policy = policy or FetchPolicy()
    if isinstance(source, bytes):
        suffix = sniff_suffix(source)
        with _temporary_file(source, suffix) as path:
            yield ResolvedSource(path, name or "document", "<bytes>")
        return
    text = os.fspath(source)
    if is_url(text):
        data, content_type, final_url = fetch_url(text, policy)
        suffix = (
            _suffix_from_url(final_url)
            or _suffix_from_content_type(content_type)
            or sniff_suffix(data)
        )
        with _temporary_file(data, suffix) as path:
            yield ResolvedSource(path, name or _name_from_url(final_url), text)
        return
    if "://" in text:
        raise SourceError(f"unsupported URL scheme in {text!r}: use http(s) or a local path")
    yield ResolvedSource(_local_path(text, policy), name or Path(text).stem, text)


def _local_path(text: str, policy: FetchPolicy) -> Path:
    if not policy.allow_local_files:
        raise SourceError("local files are disabled: pass a URL or the document's bytes")
    path = Path(text).expanduser()
    if policy.base_dir is not None:
        root = policy.base_dir.expanduser().resolve()
        path = (root / path).resolve()
        if not path.is_relative_to(root):
            raise SourceError(f"path must stay inside {root}")
    if not path.is_file():
        raise SourceError(f"file not found: {text}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise SourceError(f"unsupported file type {path.suffix!r}; supported: {supported}")
    return path


# ---- downloads ---------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface redirects to the caller, so every hop is checked against the policy."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _check_host(url: str, policy: FetchPolicy) -> None:
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"}:
        raise SourceError(f"unsupported URL scheme {parts.scheme!r}: use http or https")
    host = parts.hostname
    if not host:
        raise SourceError(f"URL has no host: {url!r}")
    if policy.allowed_hosts is not None and host.lower() not in policy.allowed_hosts:
        raise SourceError(f"host {host!r} is not in the allowed hosts")
    if policy.allow_private_hosts:
        return
    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SourceError(f"cannot resolve host {host!r}: {exc}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        mapped = getattr(address, "ipv4_mapped", None)
        if not (mapped or address).is_global:
            raise SourceError(
                f"host {host!r} resolves to a non-public address ({address}); to allow it, "
                "set DOCFUNNEL_ALLOW_PRIVATE_URLS=1 (FetchPolicy.allow_private_hosts in Python)"
            )


def fetch_url(url: str, policy: FetchPolicy | None = None) -> tuple[bytes, str | None, str]:
    """Download ``url`` under ``policy``; return ``(body, content_type, final_url)``."""
    from docfunnel import __version__

    policy = policy or FetchPolicy()
    if not policy.allow_urls:
        raise SourceError("URL input is disabled: pass a local path or the document's bytes")
    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    for _ in range(policy.max_redirects + 1):
        _check_host(current, policy)
        # The scheme is checked in _check_host: only http and https reach this point.
        request = urllib.request.Request(
            current, headers={"User-Agent": f"docfunnel/{__version__}"}
        )
        try:
            with opener.open(request, timeout=policy.timeout_s) as response:
                return _read_capped(response, policy.max_bytes), _content_type(response), current
        except urllib.error.HTTPError as exc:
            location = exc.headers.get("Location") if exc.code in _REDIRECT_CODES else None
            if location is None:
                raise SourceError(f"download failed: HTTP {exc.code} for {current}") from exc
            current = urljoin(current, location)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SourceError(f"download failed for {current}: {exc}") from exc
    raise SourceError(f"too many redirects (more than {policy.max_redirects}) for {url}")


def _read_capped(response: Any, max_bytes: int) -> bytes:
    declared = response.headers.get("Content-Length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise SourceError(f"document is larger than the {max_bytes:,}-byte limit")
    chunks: list[bytes] = []
    size = 0
    while chunk := response.read(_CHUNK):
        size += len(chunk)
        if size > max_bytes:
            raise SourceError(f"document is larger than the {max_bytes:,}-byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _content_type(response: Any) -> str | None:
    value = response.headers.get("Content-Type")
    return value.split(";", 1)[0].strip().lower() if value else None


# ---- file types ---------------------------------------------------------------------


def _suffix_from_url(url: str) -> str | None:
    suffix = PurePosixPath(unquote(urlsplit(url).path)).suffix.lower()
    return suffix if suffix in SUPPORTED_SUFFIXES else None


def _suffix_from_content_type(content_type: str | None) -> str | None:
    return _CONTENT_TYPES.get(content_type or "")


def _name_from_url(url: str) -> str:
    stem = PurePosixPath(unquote(urlsplit(url).path)).stem
    return stem or urlsplit(url).hostname or "document"


def sniff_suffix(data: bytes) -> str:
    """Guess the file type from its first bytes."""
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:2] == b"BM" and data[6:10] == b"\x00\x00\x00\x00":  # reserved header bytes
        return ".bmp"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise SourceError(
            "unknown document type: expected PDF, PNG, JPEG, TIFF, WebP, BMP or UTF-8 text"
        ) from None
    return ".txt"


@contextmanager
def _temporary_file(data: bytes, suffix: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="docfunnel-") as directory:
        path = Path(directory) / f"document{suffix}"
        path.write_bytes(data)
        yield path
