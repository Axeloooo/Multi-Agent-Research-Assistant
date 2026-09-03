import importlib
import sys
from types import ModuleType
from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    convert_to_messages,
)


class StopAfterSearch(Exception):
    pass


class RecordingSearchAgent:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def invoke(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        raise StopAfterSearch


class RecordingReaderAgent:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def invoke(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        raise StopAfterSearch


def test_search_stage_sends_a_coercible_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search_agent = RecordingSearchAgent()
    fake_agents = ModuleType("src.agents.agents")
    fake_agents.build_search_agent = lambda: search_agent
    fake_agents.build_reader_agent = lambda: None
    fake_agents.writer_chain = None
    fake_agents.critic_chain = None
    monkeypatch.setitem(sys.modules, "src.agents.agents", fake_agents)
    sys.modules.pop("src.pipelines.pipeline", None)

    try:
        pipeline = importlib.import_module("src.pipelines.pipeline")

        with pytest.raises(StopAfterSearch):
            pipeline.run_research_pipeline("topic")

        assert search_agent.payload is not None
        messages = convert_to_messages(search_agent.payload["messages"])
        assert messages == [
            HumanMessage(
                content=("Find recent, reliable and detailed information about: topic")
            )
        ]
    finally:
        sys.modules.pop("src.pipelines.pipeline", None)


def test_reader_receives_urls_from_search_tool_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search_agent = RecordingSearchAgent()
    search_agent.invoke = lambda payload: {
        "messages": [
            HumanMessage(content="Find sources"),
            ToolMessage(
                content=(
                    "Title: Source\n"
                    "URL: https://example.com/source\n"
                    "Snippet: Details"
                ),
                tool_call_id="search-call",
            ),
            AIMessage(content="The search found relevant information."),
        ]
    }
    reader_agent = RecordingReaderAgent()
    fake_agents = ModuleType("src.agents.agents")
    fake_agents.build_search_agent = lambda: search_agent
    fake_agents.build_reader_agent = lambda: reader_agent
    fake_agents.writer_chain = None
    fake_agents.critic_chain = None
    monkeypatch.setitem(sys.modules, "src.agents.agents", fake_agents)
    sys.modules.pop("src.pipelines.pipeline", None)

    try:
        pipeline = importlib.import_module("src.pipelines.pipeline")

        with pytest.raises(StopAfterSearch):
            pipeline.run_research_pipeline("topic")

        assert reader_agent.payload is not None
        reader_message = convert_to_messages(reader_agent.payload["messages"])[0]
        assert "https://example.com/source" in reader_message.content
        assert "The search found relevant information." in reader_message.content
    finally:
        sys.modules.pop("src.pipelines.pipeline", None)
