import asyncio
import inspect
import json
import logging
import os
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

try:
    from agent_framework import tool as agent_tool
except Exception:  # pragma: no cover - keeps local tests lightweight before optional deps are installed

    def agent_tool(*args, **kwargs):
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return args[0]

        def decorator(func):
            return func

        return decorator


def agent_framework_enabled() -> bool:
    return bool(os.getenv("AZURE_AI_PROJECT_ENDPOINT"))


def _response_to_text(response: Any) -> str:
    for attr in ("text", "content", "message"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return str(response)


def _parse_json_response(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text.strip())
        return value if isinstance(value, dict) else {"value": value}
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\{\[]", text):
        try:
            value, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else {"value": value}
    return None


async def _close_async_resource(resource: Any) -> None:
    close = getattr(resource, "close", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:  # pragma: no cover - cleanup best effort
        logger.warning("Failed to close Agent Framework resource %s: %s", type(resource).__name__, exc)


async def _run_agent_async(
    agent_name: str,
    instructions: str,
    prompt: str,
    deployment: str,
    tools: list[Callable] | None = None,
) -> dict[str, Any] | None:
    from agent_framework.azure import AzureAIAgentClient
    from azure.identity.aio import DefaultAzureCredential

    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "").strip()
    if not project_endpoint:
        raise RuntimeError("Set AZURE_AI_PROJECT_ENDPOINT to use Microsoft Agent Framework.")

    credential = DefaultAzureCredential()
    client = AzureAIAgentClient(
        project_endpoint=project_endpoint,
        model_deployment_name=deployment,
        credential=credential,
        agent_name=agent_name,
    )
    agent = client.as_agent(name=agent_name, instructions=instructions, tools=tools or [])

    try:
        active_agent = agent
        if hasattr(agent, "__aenter__"):
            active_agent = await agent.__aenter__() or agent
        response = await active_agent.run(prompt)
        return _parse_json_response(_response_to_text(response))
    finally:
        if hasattr(agent, "__aexit__"):
            await agent.__aexit__(None, None, None)
        await _close_async_resource(client)
        await _close_async_resource(credential)


def run_agent_json(
    agent_name: str,
    instructions: str,
    prompt: str,
    deployment: str,
    tools: list[Callable] | None = None,
) -> dict[str, Any] | None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run_agent_async(agent_name, instructions, prompt, deployment, tools=tools))

    raise RuntimeError("Agent Framework JSON calls require a synchronous context without an active event loop.")
