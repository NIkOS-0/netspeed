"""Command-line interface for sequential download measurements."""

import argparse
import os
import sys
from dataclasses import dataclass

from netspeed.measure import (
    DEFAULT_USER_AGENT,
    MeasureError,
    measure,
    summarize,
)
from netspeed.report import render

ENV_REQUESTS = "NETSPEED_REQUESTS"
ENV_COOLDOWN = "NETSPEED_COOLDOWN"
ENV_TIMEOUT = "NETSPEED_TIMEOUT"
ENV_CONNECT_TIMEOUT = "NETSPEED_CONNECT_TIMEOUT"
ENV_WARMUP = "NETSPEED_WARMUP"
ENV_OUTPUT = "NETSPEED_OUTPUT"
ENV_USER_AGENT = "NETSPEED_USER_AGENT"
ENV_ON_ERROR = "NETSPEED_ON_ERROR"


class ConfigError(Exception):
    """Environment or arguments cannot be used."""


@dataclass(frozen=True)
class Settings:
    """Resolved run configuration. CLI flags already override the environment."""

    url: str
    requests: int
    cooldown: float
    timeout: float
    connect_timeout: float | None
    warmup: int
    output: str
    user_agent: str
    on_error: str


def main(argv: list[str] | None = None) -> int:
    """Measure ``url`` and print the summary. Returns a process exit code."""
    try:
        settings = parse_settings(argv)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    try:
        samples = measure(
            settings.url,
            requests=settings.requests,
            cooldown=settings.cooldown,
            timeout=settings.timeout,
            connect_timeout=settings.connect_timeout,
            warmup=settings.warmup,
            user_agent=settings.user_agent,
            on_error=settings.on_error,
        )
    except MeasureError as exc:
        print(exc, file=sys.stderr)
        return 1
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    summary = summarize(samples)
    sys.stdout.write(render(summary, settings.output))
    return 0


def parse_settings(argv: list[str] | None = None) -> Settings:
    """Build settings from argv, then the environment, then built-in defaults."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _reject_out_of_range(args)
    return Settings(
        url=args.url,
        requests=args.requests,
        cooldown=args.cooldown,
        timeout=args.timeout,
        connect_timeout=args.connect_timeout,
        warmup=args.warmup,
        output=args.output,
        user_agent=args.user_agent,
        on_error=args.on_error,
    )


def build_parser() -> argparse.ArgumentParser:
    """Parser whose defaults are read from the environment at call time."""
    parser = argparse.ArgumentParser(
        prog="netspeed",
        description="Последовательно скачивает адрес и печатает среднюю скорость.",
        epilog="Пример: netspeed https://example.com/large-image.jpg -n 10 -c 0.5",
    )
    parser.add_argument("url", help="Адрес файла, который нужно скачать")
    parser.add_argument(
        "-n",
        "--requests",
        type=_at_least_one,
        default=_env_int(ENV_REQUESTS, 10),
        help=f"Число запросов в замере (по умолчанию 10, {ENV_REQUESTS})",
    )
    parser.add_argument(
        "-c",
        "--cooldown",
        type=_non_negative_float,
        default=_env_float(ENV_COOLDOWN, 0.0),
        help=f"Пауза между запросами в секундах (по умолчанию 0, {ENV_COOLDOWN})",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=_positive_float,
        default=_env_float(ENV_TIMEOUT, 30.0),
        help=f"Таймаут одного запроса в секундах (по умолчанию 30, {ENV_TIMEOUT})",
    )
    parser.add_argument(
        "--connect-timeout",
        type=_positive_float,
        default=_env_optional_float(ENV_CONNECT_TIMEOUT),
        help=(
            "Таймаут установки соединения в секундах "
            f"(по умолчанию как --timeout, {ENV_CONNECT_TIMEOUT})"
        ),
    )
    parser.add_argument(
        "--warmup",
        type=_non_negative_int,
        default=_env_int(ENV_WARMUP, 0),
        help=f"Сколько первых запросов отбросить (по умолчанию 0, {ENV_WARMUP})",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default=_env_choice(ENV_OUTPUT, "text", {"text", "json"}),
        help=f"Формат отчёта: text или json (по умолчанию text, {ENV_OUTPUT})",
    )
    parser.add_argument(
        "--user-agent",
        default=_env_str(ENV_USER_AGENT, DEFAULT_USER_AGENT),
        help=f"Заголовок User-Agent ({ENV_USER_AGENT})",
    )
    parser.add_argument(
        "--on-error",
        choices=("fail", "skip"),
        default=_env_choice(ENV_ON_ERROR, "fail", {"fail", "skip"}),
        help="fail останавливает прогон, skip пропускает сбойный запрос (по умолчанию fail)",
    )
    return parser


def _reject_out_of_range(args: argparse.Namespace) -> None:
    """Defaults taken from the environment skip argparse type converters."""
    if args.requests < 1:
        raise ConfigError("число запросов должно быть больше нуля")
    if args.cooldown < 0:
        raise ConfigError("кулдаун не может быть отрицательным")
    if args.timeout <= 0:
        raise ConfigError("таймаут должен быть больше нуля")
    if args.connect_timeout is not None and args.connect_timeout <= 0:
        raise ConfigError("таймаут соединения должен быть больше нуля")
    if args.warmup < 0:
        raise ConfigError("прогрев не может быть отрицательным")


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} должно быть целым числом, получено {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} должно быть числом, получено {raw!r}") from exc


def _env_optional_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} должно быть числом, получено {raw!r}") from exc


def _env_choice(name: str, default: str, allowed: set[str]) -> str:
    raw = _env_str(name, default)
    if raw not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ConfigError(f"{name} должно быть одним из: {choices}")
    return raw


def _at_least_one(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("ожидается целое число больше нуля")
    return value


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("ожидается целое число не меньше нуля")
    return value


def _positive_float(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("ожидается число больше нуля")
    return value


def _non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("ожидается число не меньше нуля")
    return value
