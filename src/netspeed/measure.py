"""Timing samples and the speed summary computed from them."""

from dataclasses import dataclass

BYTES_PER_MEGABYTE = 1_000_000


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
