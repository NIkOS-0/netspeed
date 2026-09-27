import json

import pytest

from netspeed.measure import Sample, summarize
from netspeed.report import render


def test_text_report_includes_average_volume_and_speed() -> None:
    summary = summarize(
        [
            Sample(duration_seconds=1.0, bytes_read=1_500_000, ok=True),
            Sample(duration_seconds=3.0, bytes_read=1_500_000, ok=True),
        ]
    )

    assert render(summary, "text") == (
        "Запросов: 2 (успешно 2)\n"
        "Среднее время: 2.000 с\n"
        "Скачано: 3.00 МБ\n"
        "Скорость: 0.75 МБ/с\n"
    )


def test_json_report_uses_decimal_megabytes() -> None:
    summary = summarize([Sample(duration_seconds=2.0, bytes_read=5_000_000, ok=True)])

    payload = json.loads(render(summary, "json"))

    assert payload == {
        "requests": 1,
        "succeeded": 1,
        "failed": 0,
        "average_seconds": 2.0,
        "total_bytes": 5_000_000,
        "downloaded_megabytes": 5.0,
        "megabytes_per_second": 2.5,
    }


def test_unknown_format_is_rejected() -> None:
    summary = summarize([Sample(duration_seconds=1.0, bytes_read=1, ok=True)])

    with pytest.raises(ValueError, match="unsupported output format"):
        render(summary, "yaml")
