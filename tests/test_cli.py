import json

import pytest

from netspeed.cli import main
from netspeed.measure import MeasureError, Sample


def test_defaults_and_text_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    def fake_measure(url: str, **kwargs: object) -> list[Sample]:
        captured["url"] = url
        captured.update(kwargs)
        return [Sample(duration_seconds=2.0, bytes_read=4_000_000, ok=True)]

    monkeypatch.setattr("netspeed.cli.measure", fake_measure)

    assert main(["https://example.com/photo.jpg"]) == 0

    assert captured["url"] == "https://example.com/photo.jpg"
    assert captured["requests"] == 10
    assert captured["cooldown"] == 0.0
    assert captured["timeout"] == 30.0
    assert captured["warmup"] == 0
    assert captured["on_error"] == "fail"
    output = capsys.readouterr().out
    assert "Среднее время: 2.000 с" in output
    assert "Скачано: 4.00 МБ" in output
    assert "Скорость: 2.00 МБ/с" in output


def test_flag_overrides_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NETSPEED_REQUESTS", "4")
    monkeypatch.setenv("NETSPEED_COOLDOWN", "3")
    captured: dict[str, object] = {}

    def fake_measure(_url: str, **kwargs: object) -> list[Sample]:
        captured.update(kwargs)
        return [Sample(duration_seconds=1.0, bytes_read=1_000, ok=True)]

    monkeypatch.setattr("netspeed.cli.measure", fake_measure)

    assert main(["https://example.com/photo.jpg", "-n", "2", "-c", "0.5"]) == 0

    assert captured["requests"] == 2
    assert captured["cooldown"] == 0.5
    assert capsys.readouterr().out.startswith("Запросов: 1")


def test_environment_is_used_when_flag_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETSPEED_REQUESTS", "7")
    monkeypatch.setenv("NETSPEED_COOLDOWN", "1.5")
    monkeypatch.setenv("NETSPEED_ON_ERROR", "skip")
    captured: dict[str, object] = {}

    def fake_measure(_url: str, **kwargs: object) -> list[Sample]:
        captured.update(kwargs)
        return [Sample(duration_seconds=1.0, bytes_read=1_000, ok=True)]

    monkeypatch.setattr("netspeed.cli.measure", fake_measure)

    assert main(["https://example.com/photo.jpg"]) == 0
    assert captured["requests"] == 7
    assert captured["cooldown"] == 1.5
    assert captured["on_error"] == "skip"


def test_json_output(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        "netspeed.cli.measure",
        lambda _url, **_kwargs: [Sample(duration_seconds=2.0, bytes_read=5_000_000, ok=True)],
    )

    assert main(["https://example.com/photo.jpg", "--output", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["megabytes_per_second"] == 2.5
    assert payload["total_bytes"] == 5_000_000


def test_failed_request_exits_with_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_measure(_url: str, **_kwargs: object) -> list[Sample]:
        raise MeasureError("timed out")

    monkeypatch.setattr("netspeed.cli.measure", fake_measure)

    assert main(["https://example.com/photo.jpg"]) == 1
    assert "timed out" in capsys.readouterr().err


def test_invalid_environment_exits_with_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NETSPEED_REQUESTS", "many")

    assert main(["https://example.com/photo.jpg"]) == 2
    assert "NETSPEED_REQUESTS" in capsys.readouterr().err


def test_url_is_required() -> None:
    with pytest.raises(SystemExit) as caught:
        main([])

    assert caught.value.code == 2
