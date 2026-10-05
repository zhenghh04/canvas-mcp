"""HTTP layer: auth, error messages, pagination, retries, and file transfer."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from canvas_mcp.client import CanvasClient, CanvasError
from canvas_mcp.config import Config

from .conftest import FakeResponse, make_config


class FakeSession:
    """A requests.Session stand-in returning a scripted sequence."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self.queue.pop(0) if self.queue else FakeResponse({})
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Retry tests must not actually wait out the backoff."""
    monkeypatch.setattr("canvas_mcp.client.time.sleep", lambda _s: None)


def test_missing_base_url_names_the_variable_and_the_shape():
    client = CanvasClient(Config(api_token="t"))
    with pytest.raises(CanvasError) as exc:
        client.require_base_url()
    assert "CANVAS_BASE_URL" in str(exc.value) and "instructure.com" in str(exc.value)


def test_missing_token_points_at_the_token_page():
    client = CanvasClient(Config(base_url="https://x.instructure.com"))
    with pytest.raises(CanvasError) as exc:
        client.require_token()
    assert "https://x.instructure.com/profile/settings" in str(exc.value)


def test_course_falls_back_to_the_default():
    client = CanvasClient(make_config())
    assert client.course("") == "12345"
    assert client.course("999") == "999"


def test_missing_course_id_errors_with_a_worked_example():
    client = CanvasClient(make_config(default_course_id=""))
    with pytest.raises(CanvasError) as exc:
        client.course("")
    assert "CANVAS_DEFAULT_COURSE_ID" in str(exc.value)
    assert "canvas_list_courses" in str(exc.value)


# -- error explanation -----------------------------------------------------


def test_401_explains_how_to_mint_a_new_token():
    client = CanvasClient(make_config())
    msg = client.explain(401, "", "courses/1")
    assert "CANVAS_API_TOKEN" in msg and "profile/settings" in msg


def test_403_rate_limit_is_distinguished_from_403_permission():
    """Canvas answers an exhausted request-cost bucket with 403, not 429, so the
    status alone cannot tell a throttle from a permissions problem. Conflating
    them sends the user to check enrollments when they should just wait."""
    client = CanvasClient(make_config())
    throttled = client.explain(403, "403 Forbidden (Rate Limit Exceeded)", "courses/1")
    denied = client.explain(403, "user not authorized", "courses/1")
    assert "Rate Limit" in throttled and "wait" in throttled
    assert "teacher/TA" in denied and "Rate Limit" not in denied


def test_404_explains_that_invisible_is_indistinguishable_from_absent():
    msg = CanvasClient(make_config()).explain(404, "", "courses/1")
    assert "enrollment" in msg


def test_422_names_the_usual_cause():
    msg = CanvasClient(make_config()).explain(422, "bad date", "assignments")
    assert "ISO 8601" in msg


# -- requests --------------------------------------------------------------


def test_request_sends_the_bearer_token():
    session = FakeSession(FakeResponse({"ok": True}))
    client = CanvasClient(make_config(), session=session)
    client.request("GET", "users/self")
    assert session.calls[0]["headers"]["Authorization"] == "Bearer fake-token"
    assert session.calls[0]["url"] == "https://example.instructure.com/api/v1/users/self"


def test_full_urls_pass_through_unmodified():
    """Pagination hands back absolute URLs; re-prefixing them would 404."""
    session = FakeSession(FakeResponse({}))
    client = CanvasClient(make_config(), session=session)
    client.request("GET", "https://example.instructure.com/api/v1/courses?page=2")
    assert session.calls[0]["url"].endswith("page=2")


def test_transient_5xx_is_retried_then_succeeds():
    session = FakeSession(FakeResponse(None, status=503, text="down"), FakeResponse({"ok": 1}))
    client = CanvasClient(make_config(max_retries=3), session=session)
    assert client.request("GET", "x").json() == {"ok": 1}
    assert len(session.calls) == 2


def test_rate_limited_403_is_retried():
    session = FakeSession(
        FakeResponse(None, status=403, text="403 Forbidden (Rate Limit Exceeded)"),
        FakeResponse({"ok": 1}),
    )
    client = CanvasClient(make_config(max_retries=3), session=session)
    assert client.request("GET", "x").json() == {"ok": 1}


def test_permission_403_is_not_retried():
    """Retrying a genuine permission failure just burns the rate-limit budget
    and delays an error the user has to act on anyway."""
    session = FakeSession(
        FakeResponse(None, status=403, text="user not authorized"), FakeResponse({"ok": 1})
    )
    client = CanvasClient(make_config(max_retries=3), session=session)
    with pytest.raises(CanvasError):
        client.request("GET", "x")
    assert len(session.calls) == 1


def test_404_is_not_retried():
    session = FakeSession(FakeResponse(None, status=404, text=""), FakeResponse({"ok": 1}))
    client = CanvasClient(make_config(max_retries=3), session=session)
    with pytest.raises(CanvasError):
        client.request("GET", "x")
    assert len(session.calls) == 1


def test_retries_are_bounded_and_then_surface_the_error():
    session = FakeSession(*[FakeResponse(None, status=503, text="down")] * 5)
    client = CanvasClient(make_config(max_retries=3), session=session)
    with pytest.raises(CanvasError, match="503"):
        client.request("GET", "x")
    assert len(session.calls) == 3


def test_connection_errors_are_retried_then_explained():
    session = FakeSession(
        requests.ConnectionError("dns"),
        requests.ConnectionError("dns"),
        requests.ConnectionError("dns"),
    )
    client = CanvasClient(make_config(max_retries=3), session=session)
    with pytest.raises(CanvasError, match="Could not reach"):
        client.request("GET", "x")
    assert len(session.calls) == 3


def test_retry_after_header_is_honoured():
    resp = FakeResponse(None, status=429, headers={"Retry-After": "7"})
    assert CanvasClient._backoff(0, resp) == 7.0


def test_retry_after_is_capped_so_a_bad_header_cannot_hang_the_call():
    resp = FakeResponse(None, status=429, headers={"Retry-After": "99999"})
    assert CanvasClient._backoff(0, resp) == 30.0


def test_garbage_retry_after_falls_back_to_exponential():
    resp = FakeResponse(None, status=429, headers={"Retry-After": "soon"})
    assert 0.5 <= CanvasClient._backoff(0, resp) <= 0.75


# -- pagination ------------------------------------------------------------


def _link(next_url: str) -> dict:
    return {"Link": f'<{next_url}>; rel="next"'}


def test_paged_follows_the_link_header():
    session = FakeSession(
        FakeResponse([{"id": 1}], headers=_link("https://example.instructure.com/api/v1/x?page=2")),
        FakeResponse([{"id": 2}]),
    )
    client = CanvasClient(make_config(), session=session)
    assert client.paged("x") == [{"id": 1}, {"id": 2}]


def test_paged_marks_truncation_instead_of_stopping_silently():
    """A silently-capped roster reads to a model as the whole class."""
    session = FakeSession(
        *[FakeResponse([{"id": i}], headers=_link("https://e/api/v1/x?p=2")) for i in range(5)]
    )
    client = CanvasClient(make_config(max_pages=2), session=session)
    out = client.paged("x")
    assert out[-1]["_truncated"] is True
    assert "CANVAS_MAX_PAGES" in out[-1]["_note"]


def test_paged_wraps_a_single_object_response():
    session = FakeSession(FakeResponse({"id": 1}))
    client = CanvasClient(make_config(), session=session)
    assert client.paged("x") == [{"id": 1}]


def test_paged_sends_params_only_on_the_first_page():
    """The next-page URL already encodes the query; re-sending params can
    override its cursor and loop forever on page 1."""
    session = FakeSession(
        FakeResponse([{"id": 1}], headers=_link("https://e/api/v1/x?page=2")), FakeResponse([])
    )
    client = CanvasClient(make_config(), session=session)
    client.paged("x", {"bucket": "past"})
    assert session.calls[0]["params"]["bucket"] == "past"
    assert session.calls[1]["params"] is None


# -- upload / download -----------------------------------------------------


def test_storage_post_never_carries_the_canvas_token(monkeypatch, tmp_path):
    """The upload_url is S3/InstFS, not Canvas. A bearer header there would hand
    a full-privilege Canvas credential to a third party that never asked."""
    path = tmp_path / "a.txt"
    path.write_text("hello")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, kwargs=kwargs)
        return FakeResponse({"id": 7}, status=201)

    monkeypatch.setattr(requests, "post", fake_post)
    CanvasClient(make_config()).post_to_storage(
        "https://s3.example/u", {"key": "v"}, path, "text/plain"
    )
    assert captured["url"] == "https://s3.example/u"
    assert not captured["kwargs"].get("headers")
    flat = repr(captured["kwargs"]).lower()
    assert "authorization" not in flat and "bearer" not in flat


def test_storage_post_sends_params_before_the_file(monkeypatch, tmp_path):
    """S3 ignores form fields that follow the file part, so upload_params must
    ride in `data` (emitted first) rather than merged into `files`."""
    path = tmp_path / "a.txt"
    path.write_text("hello")
    captured = {}
    monkeypatch.setattr(
        requests, "post", lambda url, **kw: (captured.update(kw), FakeResponse({"id": 1}, 201))[1]
    )
    CanvasClient(make_config()).post_to_storage(
        "https://s3/u", {"key": "v", "policy": "p"}, path, "text/plain"
    )
    assert captured["data"] == {"key": "v", "policy": "p"}
    assert set(captured["files"]) == {"file"}


def test_storage_redirect_is_confirmed_with_auth(monkeypatch, tmp_path):
    """A 3xx means "now GET the Location" — and that one DOES need our token."""
    path = tmp_path / "a.txt"
    path.write_text("hello")
    monkeypatch.setattr(
        requests,
        "post",
        lambda url, **kw: FakeResponse(None, 303, {"Location": "https://c/api/v1/files/9"}),
    )
    session = FakeSession(FakeResponse({"id": 9}))
    client = CanvasClient(make_config(), session=session)
    assert client.post_to_storage("https://s3/u", {}, path, "text/plain")["id"] == 9
    assert session.calls[0]["headers"]["Authorization"] == "Bearer fake-token"


def test_storage_redirect_without_location_is_an_error(monkeypatch, tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("hello")
    monkeypatch.setattr(requests, "post", lambda url, **kw: FakeResponse(None, 302, {}))
    with pytest.raises(CanvasError, match="no Location"):
        CanvasClient(make_config()).post_to_storage("https://s3/u", {}, path, "text/plain")


def test_storage_non_json_success_is_an_error_not_a_silent_pass(monkeypatch, tmp_path):
    """A 200 with an HTML body means the upload did not land; returning it as
    success reports a file that does not exist."""
    path = tmp_path / "a.txt"
    path.write_text("hello")
    monkeypatch.setattr(requests, "post", lambda url, **kw: FakeResponse(None, 200, text="<html>"))
    with pytest.raises(CanvasError, match="non-JSON"):
        CanvasClient(make_config()).post_to_storage("https://s3/u", {}, path, "text/plain")


def test_upload_without_an_upload_url_is_an_error():
    session = FakeSession(FakeResponse({"message": "quota exceeded"}))
    client = CanvasClient(make_config(), session=session)
    with pytest.raises(CanvasError, match="upload_url"):
        client.upload_file("1", Path(__file__), "t.py", "course files", "rename")


class _StreamResponse:
    def __init__(self, chunks, status=200):
        self._chunks = chunks
        self.status_code = status

    def iter_content(self, chunk_size=0):
        return iter(self._chunks)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_streams_to_disk_without_the_token(monkeypatch, tmp_path):
    """Canvas file URLs are pre-signed; they carry their own authorisation."""
    captured = {}
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, **kw: (captured.update(url=url, kwargs=kw), _StreamResponse([b"ab", b"cd"]))[1],
    )
    dest = tmp_path / "sub" / "f.bin"
    assert CanvasClient(make_config()).download("https://files/x", dest) == 4
    assert dest.read_bytes() == b"abcd"
    assert "headers" not in captured["kwargs"]


def test_download_of_an_expired_url_explains_itself(monkeypatch, tmp_path):
    monkeypatch.setattr(requests, "get", lambda url, **kw: _StreamResponse([], status=403))
    with pytest.raises(CanvasError, match="expire"):
        CanvasClient(make_config()).download("https://files/x", tmp_path / "f")
