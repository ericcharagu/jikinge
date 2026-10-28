import asyncio
import time
from functools import wraps
from typing import Any

from qwen_agent.agents import Assistant
from qwen_agent.llm.base import ModelServiceError

from config import llm_configuration
from domain.excepts import QwenErrorException


def agent_timer(func):
    """Creates a decorator for each agent that calculates the time taken per request handling.

    Args:
        func (_type_): function

    Returns:
        The wrapped function
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):

        # Start time
        time_start: float = time.perf_counter()

        # Get the agent name
        agent_name: str = kwargs["agent_name"]

        # Run the function
        result = await func(*args, **kwargs)

        # Time taken
        time_taken: float = time.perf_counter() - time_start

        # Result dict
        result_dict: dict[str, Any | str | float] = {
            "agent_name": agent_name,
            "time_taken": time_taken,
            "response": result,
        }
        return result_dict

    return wrapper


@agent_timer
async def run_assistant_async(
    agent_name: str,
    system_message: str,
    messages: list[dict[str, Any]],
    function_list: list[str] = list,
    files: list[str] = list,
) -> str:
    """
    Run a Qwen Assistant in a thread pool since it's synchronous.
    """
    try:

        def _run_sync():
            final_response = []
            bot = Assistant(
                llm=llm_configuration,
                name=agent_name,
                system_message=system_message,
                function_list=function_list,
                files=files,
            )
            for response in bot.run(messages=messages):
                final_response.extend(response)
            return final_response[-1].get("content") if final_response else ""

        return await asyncio.to_thread(_run_sync)
    except ModelServiceError as e:
        raise QwenErrorException(e)
