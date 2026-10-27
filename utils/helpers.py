import json
import time
from functools import wraps
from typing import Any

import httpx
from loguru import logger
from qwen_agent.llm.base import ModelServiceError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

retry_decorator = retry(
    stop=stop_after_attempt(3),  # Try 3 times
    wait=wait_exponential(multiplier=1, min=2, max=5),  # Exponential backoff
    retry=retry_if_exception_type(
        (
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.ReadTimeout,
            json.decoder.JSONDecodeError,
            ModelServiceError,
        )
    ),
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying function (attempt {retry_state.attempt_number}/3) after error: {retry_state.outcome.exception()}"
    ),
)


def function_timer(func):
    """
    A decorator that times an async function and returns a dict with the result and timing.
    Args:
        func: The function being wrapped
    Returns:
        Coroutine of the wrapped function
    """

    @wraps(func)
    async def wrapper(*args, **kwargs) -> dict[str, Any | float | str]:
        """
        Handle the function
        Args:
            args: All arguments used by the function
            kwargs: All keyword arguments used by the function

        Returns:
            dict containing the results, timing and metrics
        """
        time_start: float = time.perf_counter()
        try:
            result: Any | str = await func(*args, **kwargs)
            status = "success"
        except Exception as e:
            # Log the error and re-raise it so the caller can handle it
            logger.error(f"Exception in {func.__name__}: {e}", exc_info=True)
            result: str = str(e)
            status = "error"
            raise
        finally:
            time_taken: float = time.perf_counter() - time_start

        return {
            "function_name": func.__name__,
            "time_taken_seconds": round(number=time_taken, ndigits=4),
            "status": status,
            "result": result,
        }

    return wrapper
