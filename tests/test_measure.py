from collections.abc import Callable

import httpx
import pytest

from netspeed.measure import MeasureError, Sample, measure, summarize


def test_summarize_averages_time_volume_and_speed() -> None:
    summary = summarize(
        [
            Sample(duration_seconds=1.0, bytes_read=1_000_000, ok=True),
            Sample(duration_seconds=9.0, bytes_read=0, ok=False, error="boom"),
            Sample(duration_seconds=3.0, bytes_read=1_000_000, ok=True),
        ]
    )

    assert summary.requested == 3
    assert summary.succeeded == 2
    assert summary.failed == 1
    assert summary.average_seconds == 2.0
    assert summary.total_bytes == 2_000_000
    assert summary.total_seconds == 4.0
    assert summary.downloaded_megabytes == 2.0
    assert summary.megabytes_per_second == 0.5


def test_summarize_is_zero_when_nothing_was_downloaded() -> None:
    summary = summarize([Sample(duration_seconds=0.0, bytes_read=100, ok=True)])

    assert summary.average_seconds == 0.0
    assert summary.megabytes_per_second == 0.0


def test_cooldown_is_excluded_from_speed() -> None:
    client = _client(b"a" * 1_000_000)
    ticks = iter([0.0, 2.0, 2.0, 4.0])
    pauses: list[float] = []

    samples = measure(
        "https://example.com/photo.jpg",
        requests=2,
        cooldown=10,
        client=client,
        sleep=pauses.append,
        clock=lambda: next(ticks),
    )
    summary = summarize(samples)

    assert pauses == [10]
    assert summary.total_seconds == 4.0
    assert summary.megabytes_per_second == 0.5
    assert client.is_closed is False


def test_requests_run_one_after_another_and_read_the_whole_body() -> None:
    active = {"count": 0}
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert active["count"] == 0
        active["count"] += 1
        calls["count"] += 1
        assert request.url == httpx.URL("https://example.com/photo.jpg")
        active["count"] -= 1
        return httpx.Response(200, content=b"12345")

    ticks = iter([0.0, 1.0, 1.0, 2.0, 2.0, 3.5])
    samples = measure(
        "https://example.com/photo.jpg",
        requests=3,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
        clock=lambda: next(ticks),
    )

    assert calls["count"] == 3
    assert [sample.bytes_read for sample in samples] == [5, 5, 5]
    assert [sample.duration_seconds for sample in samples] == [1.0, 1.0, 1.5]


def test_warmup_requests_are_not_included() -> None:
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, content=b"x" * calls["count"])

    samples = measure(
        "https://example.com/photo.jpg",
        requests=2,
        warmup=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
        clock=_clock(),
    )

    assert calls["count"] == 3
    assert [sample.bytes_read for sample in samples] == [2, 3]


def test_skip_keeps_going_after_a_failed_request() -> None:
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, content=b"no")
        return httpx.Response(200, content=b"ok")

    samples = measure(
        "https://example.com/photo.jpg",
        requests=2,
        on_error="skip",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
        clock=_clock(),
    )

    assert calls["count"] == 2
    assert samples[0].ok is False
    assert samples[1].ok is True
    assert samples[1].bytes_read == 2
    assert summarize(samples).succeeded == 1


def test_fail_stops_on_the_first_error() -> None:
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(500, content=b"no")

    with pytest.raises(MeasureError):
        measure(
            "https://example.com/photo.jpg",
            requests=3,
            on_error="fail",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _seconds: None,
            clock=_clock(),
        )

    assert calls["count"] == 1


def test_user_agent_is_sent() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(200, content=b"a")

    measure(
        "https://example.com/photo.jpg",
        requests=1,
        user_agent="netspeed-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
        clock=_clock(),
    )

    assert seen == ["netspeed-test"]


def test_owned_client_uses_timeouts_and_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

        def stream(self, *_args: object, **_kwargs: object) -> object:
            raise httpx.ConnectError("offline")

        def close(self) -> None:
            created["closed"] = True

    monkeypatch.setattr(httpx, "Client", FakeClient)

    with pytest.raises(MeasureError):
        measure(
            "https://example.com/photo.jpg",
            requests=1,
            timeout=12,
            connect_timeout=3,
            user_agent="ua",
        )

    assert created["headers"] == {"User-Agent": "ua"}
    assert created["follow_redirects"] is True
    timeout = created["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 3.0
    assert timeout.read == 12.0
    assert created["closed"] is True


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"requests": 0}, "requests"),
        ({"cooldown": -1}, "cooldown"),
        ({"timeout": 0}, "timeout"),
        ({"connect_timeout": 0}, "connect_timeout"),
        ({"warmup": -1}, "warmup"),
        ({"on_error": "retry"}, "on_error"),
    ],
)
def test_rejects_invalid_settings(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        measure("https://example.com/photo.jpg", client=_client(b"a"), **kwargs)  # type: ignore[arg-type]


def _client(body: bytes) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _clock() -> Callable[[], float]:
    step = {"value": 0.0}

    def clock() -> float:
        step["value"] += 1.0
        return step["value"]

    return clock
