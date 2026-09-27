"""Sequential downloads and the speed summary computed from them."""

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

BYTES_PER_MEGABYTE = 1_000_000
DEFAULT_USER_AGENT = "netspeed/0.1.0"


@dataclass(frozen=True)
class Sample:
    """One finished download attempt."""

    duration_seconds: float
    bytes_read: int
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class Summary:
    """Aggregate of measured attempts. Pause between requests is not included."""

    requested: int
    succeeded: int
    failed: int
    average_seconds: float
    total_bytes: int
    total_seconds: float
    megabytes_per_second: float

    @property
    def downloaded_megabytes(self) -> float:
        return self.total_bytes / BYTES_PER_MEGABYTE


class MeasureError(Exception):
    """A request failed and the run was configured to stop."""


def summarize(samples: list[Sample]) -> Summary:
    """Average time, downloaded volume, and MB/s.

    Failed attempts stay in the counts and do not affect time, volume, or speed.
    Speed is total megabytes (10^6 bytes) divided by the sum of download durations.
    """
    successful = [sample for sample in samples if sample.ok]
    total_bytes = sum(sample.bytes_read for sample in successful)
    total_seconds = sum(sample.duration_seconds for sample in successful)
    succeeded = len(successful)
    average_seconds = total_seconds / succeeded if succeeded else 0.0
    if total_seconds > 0:
        megabytes_per_second = (total_bytes / BYTES_PER_MEGABYTE) / total_seconds
    else:
        megabytes_per_second = 0.0
    return Summary(
        requested=len(samples),
        succeeded=succeeded,
        failed=len(samples) - succeeded,
        average_seconds=average_seconds,
        total_bytes=total_bytes,
        total_seconds=total_seconds,
        megabytes_per_second=megabytes_per_second,
    )


def measure(
    url: str,
    *,
    requests: int = 10,
    cooldown: float = 0.0,
    timeout: float = 30.0,
    connect_timeout: float | None = None,
    warmup: int = 0,
    user_agent: str = DEFAULT_USER_AGENT,
    on_error: str = "fail",
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.perf_counter,
) -> list[Sample]:
    """Download ``url`` one request at a time and return measured samples.

    ``warmup`` leading requests are executed and then discarded. ``sleep`` runs
    between attempts, including warmup, and does not run after the last one.
    """
    _validate(requests, cooldown, timeout, connect_timeout, warmup, on_error)
    owns_client = client is None
    if client is None:
        connect = timeout if connect_timeout is None else connect_timeout
        client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=connect),
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )
    samples: list[Sample] = []
    total_runs = warmup + requests
    try:
        for index in range(total_runs):
            sample = _download_once(client, url, clock, user_agent)
            if not sample.ok and on_error == "fail":
                raise MeasureError(sample.error or "request failed")
            if index >= warmup:
                samples.append(sample)
            if cooldown > 0 and index < total_runs - 1:
                sleep(cooldown)
        return samples
    finally:
        if owns_client:
            client.close()


def _download_once(
    client: httpx.Client,
    url: str,
    clock: Callable[[], float],
    user_agent: str,
) -> Sample:
    started = clock()
    try:
        with client.stream("GET", url, headers={"User-Agent": user_agent}) as response:
            response.raise_for_status()
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
    except httpx.HTTPError as exc:
        return Sample(
            duration_seconds=clock() - started,
            bytes_read=0,
            ok=False,
            error=str(exc),
        )
    return Sample(duration_seconds=clock() - started, bytes_read=total, ok=True)


def _validate(
    requests: int,
    cooldown: float,
    timeout: float,
    connect_timeout: float | None,
    warmup: int,
    on_error: str,
) -> None:
    if requests < 1:
        raise ValueError("requests must be at least 1")
    if cooldown < 0:
        raise ValueError("cooldown must be zero or positive")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if connect_timeout is not None and connect_timeout <= 0:
        raise ValueError("connect_timeout must be positive")
    if warmup < 0:
        raise ValueError("warmup must be zero or positive")
    if on_error not in {"fail", "skip"}:
        raise ValueError("on_error must be 'fail' or 'skip'")
