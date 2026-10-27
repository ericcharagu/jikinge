import json
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

api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=5),
    retry=retry_if_exception_type(
        (
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.ReadTimeout,
            json.decoder.JSONDecodeError,
            ModelServiceError,
        )
    ),
    reraise=True,
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying API call (attempt {retry_state.attempt_number}/3) "
        f"after error: {retry_state.outcome.exception()}"
    ),
)


def _log_response_body(response: httpx.Response, url: str) -> None:
    """Best-effort pretty-print of the response body for debugging."""
    try:
        body = response.json()
    except Exception:
        body = response.text
    logger.error(f"API error: url={url} status={response.status_code} body={body}")


@api_retry
async def post_api_request(
    url: str, payload: dict[str, Any], headers: dict[str, Any] | None = None
):
    headers = headers or {}
    async with httpx.AsyncClient() as client:
        try:
            api_response = await client.post(
                url, json=payload, headers=headers, timeout=120
            )
            if api_response.is_error:
                _log_response_body(api_response, url)
            api_response.raise_for_status()
            return api_response
        except httpx.HTTPStatusError:
            # 4xx/5xx already logged above; re-raise so the caller sees it
            raise
        except httpx.ConnectError as err:
            logger.error(f"Error connecting to {url}: {err}")
            raise
        except httpx.TimeoutException as err:
            logger.error(f"Timeout calling {url}: {err}")
            raise
        except httpx.RequestError as err:
            logger.error(f"Unexpected HTTP error calling {url}: {err}")
            raise


@api_retry
async def get_api_request(url: str):
    async with httpx.AsyncClient() as client:
        try:
            api_response = await client.get(url, timeout=60)
            if api_response.is_error:
                _log_response_body(api_response, url)
            api_response.raise_for_status()
            return api_response
        except httpx.HTTPStatusError:
            raise
        except httpx.ConnectError as err:
            logger.error(f"Error connecting to {url}: {err}")
            raise
        except httpx.TimeoutException as err:
            logger.error(f"Timeout calling {url}: {err}")
            raise
        except httpx.RequestError as err:
            logger.error(f"Unexpected HTTP error calling {url}: {err}")
            raise
