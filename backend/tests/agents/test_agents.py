import importlib
import sys
from typing import Any, get_args, get_origin, get_type_hints

import dotenv
import langchain.agents
import langchain.chat_models
import pytest
from langchain.agents.middleware.types import (
    AgentState,
    InputAgentState,
    OutputAgentState,
)
from langchain_core.runnables import RunnableLambda
from langgraph.graph.state import CompiledStateGraph


def test_agent_builder_return_types_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_agent = object()
    fake_model = RunnableLambda(lambda value: value)
    agent_options: list[dict[str, object]] = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: False)
    monkeypatch.setattr(
        langchain.agents,
        "create_agent",
        lambda **kwargs: agent_options.append(kwargs) or fake_agent,
    )
    monkeypatch.setattr(
        langchain.chat_models,
        "init_chat_model",
        lambda **kwargs: fake_model,
    )
    sys.modules.pop("src.agents.agents", None)
    agents = importlib.import_module("src.agents.agents")

    try:
        for builder in (agents.build_search_agent, agents.build_reader_agent):
            return_type = get_type_hints(builder)["return"]

            assert builder() is fake_agent
            assert get_origin(return_type) is CompiledStateGraph
            assert get_args(return_type) == (
                AgentState[Any],
                Any,
                InputAgentState,
                OutputAgentState[Any],
            )
        assert "web_search exactly once" in str(agent_options[0]["system_prompt"])
        assert "scrape_url exactly once" in str(agent_options[1]["system_prompt"])
    finally:
        sys.modules.pop("src.agents.agents", None)
