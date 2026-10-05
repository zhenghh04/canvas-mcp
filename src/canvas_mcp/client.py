"""HTTP access to the Canvas LMS REST API.

One :class:`CanvasClient` owns the session, the bearer token, pagination,
retries, and the file-upload dance. Tools never touch ``requests`` directly, so
the token has exactly one place it can leak from and the retry policy has
exactly one place it can drift in.
"""

from __future__ import annotations

import mimetypes
import random
import re
import time
from pathlib import Path
from typing import Any

import requests

from .config import Config
from .formatting import format_payload

#: Canvas paginates with a Link header rather than a cursor field in the body.
_NEXT_RE = re.compile(r'<([^>]+)>\s*;\s*rel="next"')

#: Canvas answers an exhausted request-cost bucket with 403 and this phrase,
#: not 429 — so the status code alone cannot distinguish it from a real
#: permission failure, and the body has to be read.
_RATE_LIMIT_MARKER = "rate limit exceeded"

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class CanvasError(RuntimeError):
    """A Canvas API failure carrying an agent-actionable remedy."""


class CanvasClient:
    """Thin, retrying wrapper over ``$CANVAS_BASE_URL/api/v1``."""

    def __init__(self, config: Config, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    # -- configuration checks ---------------------------------------------

    def require_base_url(self) -> str:
        if not self.config.base_url:
            raise CanvasError(
                "CANVAS_BASE_URL is not set. Point it at your institution's Canvas "
                "host — the scheme and domain you see in the browser, e.g. "
                "https://myschool.instructure.com (no trailing /api/v1)."
            )
        return self.config.base_url

    def require_token(self) -> str:
        self.require_base_url()
        if not self.config.api_token:
            raise CanvasError(
                "CANVAS_API_TOKEN is not set. Create one at "
                f"{self.config.token_page_url} (Approved Integrations > "
                "+ New Access Token), then put it in your .env or your MCP "
                "client's env block and restart the server."
            )
        return self.config.api_token

    def course(self, course_id: str | int | None) -> str:
        """Resolve a course id, falling back to ``CANVAS_DEFAULT_COURSE_ID``."""
        cid = str(course_id or "").strip() or self.config.default_course_id
        if not cid:
            raise CanvasError(
                "No course_id given and CANVAS_DEFAULT_COURSE_ID is unset. Pass the "
                "numeric id from the course URL — in "
                f"{self.config.base_url or 'https://<your-canvas>'}/courses/12345 "
                "the id is 12345. canvas_list_courses will list the ones you teach."
            )
        return cid

    # -- error messages ----------------------------------------------------

    def explain(self, status: int, body: str, path: str) -> str:
        """Map an HTTP status onto a message that says what to do next."""
        base = self.config.base_url or "<your Canvas host>"
        if status == 401:
            return (
                f"401 Unauthorized on {path}. CANVAS_API_TOKEN is missing, expired, "
                f"or revoked. Generate a new one at {self.config.token_page_url} "
                "(Approved Integrations > + New Access Token) and update your .env "
                "or MCP client env block, then restart the server."
            )
        if status == 403:
            if _RATE_LIMIT_MARKER in body.lower():
                return (
                    f"403 Rate Limit Exceeded on {path}. Canvas throttles by request "
                    "cost, not request count, so a few wide listings can exhaust the "
                    "bucket. Retried and still throttled — wait a minute, then narrow "
                    "the query (lower max_pages, add a filter)."
                )
            return (
                f"403 Forbidden on {path}. The token is valid but lacks permission: "
                "either your account restricts this endpoint, or you are not enrolled "
                "as a teacher/TA/designer in this course. Admin-only endpoints need an "
                f"admin token. Body: {body[:300]}"
            )
        if status == 404:
            return (
                f"404 Not Found on {path}. Check the id — in {base}/courses/12345 the "
                "course id is 12345. Canvas also returns 404 for objects that exist "
                "but are invisible to you, so confirm your enrollment in the course."
            )
        if status == 422:
            return (
                f"422 Unprocessable Entity on {path}. Canvas rejected the parameters — "
                "usually a malformed date (it wants ISO 8601 UTC like "
                f"2026-09-10T04:59:59Z), or a required field left empty. Body: {body[:400]}"
            )
        return f"HTTP {status} on {path}. Body: {body[:500]}"

    # -- requests ----------------------------------------------------------

    def _should_retry(self, status: int, body: str) -> bool:
        if status in _RETRY_STATUSES:
            return True
        return status == 403 and _RATE_LIMIT_MARKER in body.lower()

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Perform one authenticated Canvas call, retrying transient failures.

        ``path`` may be a bare path under ``/api/v1`` or a full URL (which is
        what the Link header hands back during pagination).
        """
        token = self.require_token()
        url = path if path.startswith("http") else f"{self.config.api_url}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        attempts = max(1, self.config.max_retries)
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self.session.request(
                    method, url, headers=headers, timeout=self.config.timeout, **kwargs
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt + 1 < attempts:
                    time.sleep(self._backoff(attempt))
                    continue
                raise CanvasError(
                    f"Could not reach {self.config.base_url}: {exc}. Check the host name, "
                    "your network, and any proxy — Canvas itself is rarely the problem here."
                ) from exc
            if resp.status_code < 400:
                return resp
            if attempt + 1 < attempts and self._should_retry(resp.status_code, resp.text):
                time.sleep(self._backoff(attempt, resp))
                continue
            raise CanvasError(self.explain(resp.status_code, resp.text, path))
        raise CanvasError(f"Could not reach {self.config.base_url}: {last_exc}")

    @staticmethod
    def _backoff(attempt: int, resp: requests.Response | None = None) -> float:
        """Seconds to wait before the next attempt.

        Honours ``Retry-After`` when Canvas sends one; otherwise exponential with
        jitter so several concurrent tool calls do not re-collide in lockstep.
        """
        if resp is not None:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(30.0, float(retry_after))
                except ValueError:
                    pass
        return min(8.0, (2**attempt) * 0.5) + random.uniform(0, 0.25)

    def get_json(self, path: str, params: dict | None = None) -> Any:
        return self.request("GET", path, params=params or {}).json()

    def paged(self, path: str, params: dict | None = None, max_pages: int | None = None) -> list:
        """Follow Canvas's Link-header pagination up to ``max_pages``.

        A capped result ends with an explicit ``_truncated`` marker rather than
        just stopping, so neither the model nor the instructor mistakes a
        partial roster for a complete one.
        """
        limit = max_pages or self.config.max_pages
        query = dict(params or {})
        query.setdefault("per_page", self.config.per_page)
        out: list = []
        url: str | None = path
        pages = 0
        while url and pages < limit:
            resp = self.request("GET", url, params=query if pages == 0 else None)
            chunk = resp.json()
            if not isinstance(chunk, list):
                return [chunk]
            out.extend(chunk)
            match = _NEXT_RE.search(resp.headers.get("Link", ""))
            url = match.group(1) if match else None
            pages += 1
        if url:
            out.append(
                {
                    "_truncated": True,
                    "_note": (
                        f"stopped after {limit} pages ({len(out)} records). Raise "
                        "CANVAS_MAX_PAGES or narrow the query — this list is incomplete."
                    ),
                }
            )
        return out

    # -- file transfer -----------------------------------------------------

    def post_to_storage(
        self, upload_url: str, upload_params: dict, path: Path, content_type: str
    ) -> dict:
        """Steps 2 and 3 of Canvas's three-step file upload.

        ``upload_url`` is **not** Canvas — it is S3 or InstFS, and the pre-signed
        ``upload_params`` are the entire authorisation. Sending our bearer token
        there would hand a full-privilege Canvas credential to a third party that
        neither needs nor expects it, so this deliberately bypasses
        :meth:`request` and builds a bare, header-free POST.

        Multipart field order matters: S3 ignores anything after the ``file``
        part, so every upload_param must be written first. ``requests`` emits
        ``data`` before ``files``, which gives us that for free.
        """
        try:
            with path.open("rb") as handle:
                resp = requests.post(
                    upload_url,
                    data=upload_params,
                    files={"file": (path.name, handle, content_type)},
                    timeout=self.config.upload_timeout,
                    allow_redirects=False,
                )
        except requests.RequestException as exc:
            raise CanvasError(f"Upload to the storage host failed: {exc}") from exc
        if resp.status_code >= 400:
            raise CanvasError(
                f"HTTP {resp.status_code} from the storage host during upload. "
                f"Body: {resp.text[:300]}"
            )
        if resp.status_code in (301, 302, 303, 307, 308):
            # "Now confirm with Canvas" — and that GET *does* need our token.
            location = resp.headers.get("Location")
            if not location:
                raise CanvasError(
                    f"Storage host returned {resp.status_code} with no Location header; "
                    "the upload cannot be confirmed."
                )
            return self.request("GET", location).json()
        try:
            return resp.json()
        except ValueError as exc:
            raise CanvasError(
                f"Storage host returned {resp.status_code} with a non-JSON body, so the "
                f"upload could not be confirmed. Body: {resp.text[:200]}"
            ) from exc

    def upload_file(
        self, course_id: str, path: Path, name: str, folder: str, on_duplicate: str
    ) -> dict:
        """Register, transfer, and confirm one course-files upload."""
        size = path.stat().st_size
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        ticket = self.request(
            "POST",
            f"courses/{course_id}/files",
            data={
                "name": name,
                "size": size,
                "content_type": content_type,
                "parent_folder_path": folder,
                "on_duplicate": on_duplicate,
            },
        ).json()
        upload_url = ticket.get("upload_url")
        if not upload_url:
            raise CanvasError(
                "Canvas did not return an upload_url, so there is nowhere to send the "
                f"bytes. Response: {format_payload(ticket, 500)}"
            )
        return self.post_to_storage(
            upload_url, ticket.get("upload_params") or {}, path, content_type
        )

    def download(self, url: str, dest: Path) -> int:
        """Stream a Canvas file URL to disk, returning the byte count.

        Canvas file URLs are pre-signed and already carry their own
        authorisation, so this sends no bearer token either.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with requests.get(url, stream=True, timeout=self.config.upload_timeout) as resp:
                if resp.status_code >= 400:
                    raise CanvasError(
                        f"HTTP {resp.status_code} downloading {dest.name}. Canvas file "
                        "URLs are pre-signed and expire; re-list the files to get a "
                        "fresh one."
                    )
                written = 0
                with dest.open("wb") as handle:
                    for block in resp.iter_content(chunk_size=65536):
                        handle.write(block)
                        written += len(block)
                return written
        except requests.RequestException as exc:
            raise CanvasError(f"Download of {dest.name} failed: {exc}") from exc

    # -- output ------------------------------------------------------------

    def fmt(self, data: Any, max_chars: int | None = None) -> str:
        """Serialise a tool result under this server's bounds and PII policy."""
        limit = self.config.max_chars if max_chars is None else max_chars
        return format_payload(data, limit, redact_pii=self.config.redact_pii)
