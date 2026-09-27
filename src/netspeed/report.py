"""Text and JSON renderings of a measurement summary."""

import json

from netspeed.measure import Summary


def render(summary: Summary, output: str) -> str:
    """Render ``summary`` as ``text`` or ``json``."""
    if output == "text":
        return render_text(summary)
    if output == "json":
        return render_json(summary)
    raise ValueError(f"unsupported output format: {output}")


def render_text(summary: Summary) -> str:
    """Human-readable report. Speed is decimal megabytes per second."""
    return (
        f"Запросов: {summary.requested} (успешно {summary.succeeded})\n"
        f"Среднее время: {summary.average_seconds:.3f} с\n"
        f"Скачано: {summary.downloaded_megabytes:.2f} МБ\n"
        f"Скорость: {summary.megabytes_per_second:.2f} МБ/с\n"
    )


def render_json(summary: Summary) -> str:
    """Machine-readable report. Megabytes are 10^6 bytes."""
    payload = {
        "requests": summary.requested,
        "succeeded": summary.succeeded,
        "failed": summary.failed,
        "average_seconds": summary.average_seconds,
        "total_bytes": summary.total_bytes,
        "downloaded_megabytes": summary.downloaded_megabytes,
        "megabytes_per_second": summary.megabytes_per_second,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
