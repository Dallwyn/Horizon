from __future__ import annotations

from tenacity import RetryError, Retrying, stop_after_attempt

from src.ai.utils import unwrap_retry_error


class _Boom(Exception):
    pass


def _make_retry_error(message: str) -> RetryError:
    def always_fails():
        raise _Boom(message)

    try:
        Retrying(stop=stop_after_attempt(1), reraise=False)(always_fails)
    except RetryError as exc:
        return exc
    raise AssertionError("Retrying did not raise RetryError")


def test_unwrap_retry_error_returns_underlying_exception() -> None:
    retry_error = _make_retry_error("400 API key not valid")

    cause = unwrap_retry_error(retry_error)

    assert isinstance(cause, _Boom)
    assert str(cause) == "400 API key not valid"


def test_unwrap_retry_error_passes_through_plain_exceptions() -> None:
    plain = ValueError("not a retry error")

    assert unwrap_retry_error(plain) is plain
