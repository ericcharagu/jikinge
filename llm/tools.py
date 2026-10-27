import asyncio
import concurrent.futures
import json
from typing import Any

from qwen_agent.tools.base import BaseTool, register_tool
from rag.vector_db import qdrant

from config import settings
from dependencies import tavily_client


@register_tool("internet_search_tool")
class TavilySearchTool(BaseTool):
    description = "A tool using Tavily API to perform internet searches"
    parameters = [
        {
            "name": "query",
            "type": "string",
            "description": "Search query for car parts, tires, or automotive products",
            "required": True,
        }
    ]

    def call(self, params: str, **kwargs) -> str:
        query = json.loads(params)["query"]
        results = tavily_client.search(query, max_results=settings.TAVILY_MAX_RESULTS)
        return json.dumps(results)


@register_tool("search_referral_document")
class ReferralDocumentSearch(BaseTool):
    description = "A tool to search internal referral program policy using vector database search."
    parameters = [
        {
            "name": "query",
            "type": "string",
            "description": "Search query regarding the referral program.",
            "required": True,
        }
    ]

    def call(self, params: str, **kwargs) -> list[dict[str, Any]]:

        query = json.loads(params)["query"]

        vector_search_results_raw = self._run_async(
            qdrant.standard_retriever.search(
                question=query, collection_name=settings.REFERRAL_COLLECTION
            )
        )
        search_results: list[dict[str, Any]] = []
        for point in vector_search_results_raw.points:
            payload = point.payload
            meta = payload.get("metadata", {})
            if not meta:
                meta = payload
            search_results.append(meta)
        return search_results

    def _run_async(self, fn):
        """Run an async function from sync code, handling existing loops properly."""
        try:
            # Check if there's already a running loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - create one and run
            return asyncio.run(fn)
        else:
            # There's a running loop - need to run in a separate thread
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, fn)
                return future.result()
