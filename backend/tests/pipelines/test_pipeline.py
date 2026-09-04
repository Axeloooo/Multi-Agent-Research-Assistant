import asyncio
import sys
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _collect(async_iterable: Any) -> list[Any]:
    async def collect() -> list[Any]:
        return [item async for item in async_iterable]

    return asyncio.run(collect())


def test_stream_research_pipeline_emits_safe_ordered_events() -> None:
    from research_assistant.pipelines.pipeline import (
        PipelineDependencies,
        stream_research_pipeline,
    )

    async def search(topic: str) -> str:
        assert topic == "topic"
        return "Search result"

    async def reader(topic: str, search_results: str) -> str:
        assert (topic, search_results) == ("topic", "Search result")
        return "Read result"

    async def writer(topic: str, research: str):
        assert topic == "topic"
        assert "Search result" in research
        yield "Report "
        yield "text"

    async def critic(report: str):
        assert report == "Report text"
        yield "Critique"

    events = _collect(
        stream_research_pipeline(
            "topic",
            PipelineDependencies(
                search=search, reader=reader, writer=writer, critic=critic
            ),
        )
    )

    assert [event.type for event in events] == [
        "agent.status",
        "agent.activity",
        "agent.output.delta",
        "agent.status",
        "agent.status",
        "agent.activity",
        "agent.output.delta",
        "agent.status",
        "agent.status",
        "agent.activity",
        "agent.activity",
        "report.delta",
        "report.delta",
        "agent.status",
        "agent.status",
        "agent.activity",
        "agent.activity",
        "critique.delta",
        "agent.status",
        "run.completed",
    ]
    assert events[-1].payload["result"] == {
        "search_results": "Search result",
        "scraped_content": "Read result",
        "report": "Report text",
        "feedback": "Critique",
    }


def test_stream_research_pipeline_times_out_search_and_skips_later_stages() -> None:
    from research_assistant.pipelines.pipeline import (
        PipelineDependencies,
        PipelineTimeouts,
        stream_research_pipeline,
    )

    async def search(topic: str) -> str:
        await asyncio.Event().wait()
        return topic

    async def reader(topic: str, search_results: str) -> str:
        raise AssertionError("reader must not run after a search timeout")

    async def writer(topic: str, research: str):
        yield "Report"

    async def critic(report: str):
        yield "Critique"

    events = _collect(
        stream_research_pipeline(
            "topic",
            PipelineDependencies(
                search=search, reader=reader, writer=writer, critic=critic
            ),
            timeouts=PipelineTimeouts(search=0.01, reader=1, writer=1, critic=1),
        )
    )

    statuses = [
        (event.agent, event.payload["status"])
        for event in events
        if event.type == "agent.status"
    ]
    assert statuses[-4:] == [
        ("search", "failed"),
        ("reader", "skipped"),
        ("writer", "skipped"),
        ("critic", "skipped"),
    ]
    assert events[-1].type == "run.failed"
    assert events[-1].payload == {"message": "Research run failed. Please try again."}


def test_stream_research_pipeline_stops_at_cancellation_boundary() -> None:
    from research_assistant.pipelines.pipeline import (
        PipelineDependencies,
        stream_research_pipeline,
    )

    cancellation_event = asyncio.Event()

    async def search(topic: str) -> str:
        cancellation_event.set()
        return "Search result"

    async def reader(topic: str, search_results: str) -> str:
        raise AssertionError("reader must not run after cancellation")

    async def writer(topic: str, research: str):
        yield "Report"

    async def critic(report: str):
        yield "Critique"

    events = _collect(
        stream_research_pipeline(
            "topic",
            PipelineDependencies(
                search=search, reader=reader, writer=writer, critic=critic
            ),
            cancellation_event,
        )
    )

    assert events[-1].type == "run.cancelled"
    assert events[-1].agent is None


def test_stream_research_pipeline_marks_later_stages_skipped_after_failure() -> None:
    from research_assistant.pipelines.pipeline import (
        PipelineDependencies,
        stream_research_pipeline,
    )

    async def search(topic: str) -> str:
        raise ValueError("provider token must not leak")

    async def reader(topic: str, search_results: str) -> str:
        raise AssertionError("reader must not run")

    async def writer(topic: str, research: str):
        yield "Report"

    async def critic(report: str):
        yield "Critique"

    events = _collect(
        stream_research_pipeline(
            "topic",
            PipelineDependencies(
                search=search, reader=reader, writer=writer, critic=critic
            ),
        )
    )

    statuses = [
        (event.agent, event.payload["status"])
        for event in events
        if event.type == "agent.status"
    ]
    assert statuses[-4:] == [
        ("search", "failed"),
        ("reader", "skipped"),
        ("writer", "skipped"),
        ("critic", "skipped"),
    ]
    assert events[-1].payload == {"message": "Research run failed. Please try again."}


def test_default_dependencies_keep_only_safe_assistant_search_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_assistant.pipelines.pipeline import run_research_pipeline

    class Agent:
        def __init__(self, response: dict[str, list[Any]]) -> None:
            self.response = response

        def invoke(
            self, payload: dict[str, Any], config: dict[str, Any]
        ) -> dict[str, list[Any]]:
            return self.response

    class Chain:
        def __init__(self, chunks: list[str]) -> None:
            self.chunks = chunks

        async def astream(self, payload: dict[str, str]):
            for chunk in self.chunks:
                yield chunk

    fake_agents = ModuleType("research_assistant.agents.agents")
    fake_agents.build_search_agent = lambda: Agent(
        {
            "messages": [
                HumanMessage(content="Find sources"),
                ToolMessage(content="raw tool payload", tool_call_id="search-call"),
                AIMessage(content="Safe search summary"),
            ]
        }
    )
    fake_agents.build_reader_agent = lambda: Agent(
        {"messages": [AIMessage(content="Safe reader summary")]}
    )
    fake_agents.build_writer_chain = lambda: Chain(["Report"])
    fake_agents.build_critic_chain = lambda: Chain(["Critique"])
    monkeypatch.setitem(sys.modules, "research_assistant.agents.agents", fake_agents)

    assert run_research_pipeline("topic") == {
        "search_results": "Safe search summary",
        "scraped_content": "Safe reader summary",
        "report": "Report",
        "feedback": "Critique",
    }


def test_default_dependencies_emit_safe_tool_lifecycle_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_assistant.pipelines.pipeline import stream_research_pipeline

    class Agent:
        def __init__(self, response: str, emit_tool_activity: bool = False) -> None:
            self.response = response
            self.emit_tool_activity = emit_tool_activity

        def invoke(
            self, payload: dict[str, Any], config: dict[str, Any]
        ) -> dict[str, list[AIMessage]]:
            if self.emit_tool_activity:
                callback = config["callbacks"][0]
                callback.on_tool_start({}, "private query", run_id=uuid4())
                callback.on_tool_end("private result", run_id=uuid4())
            return {"messages": [AIMessage(content=self.response)]}

    class Chain:
        async def astream(self, payload: dict[str, str]):
            yield "Report"

    fake_agents = ModuleType("research_assistant.agents.agents")
    fake_agents.build_search_agent = lambda: Agent("Search", emit_tool_activity=True)
    fake_agents.build_reader_agent = lambda: Agent("Reader")
    fake_agents.build_writer_chain = Chain
    fake_agents.build_critic_chain = Chain
    monkeypatch.setitem(sys.modules, "research_assistant.agents.agents", fake_agents)

    events = _collect(stream_research_pipeline("topic"))
    activities = [event for event in events if event.type == "agent.activity"]

    assert [(event.agent, event.payload) for event in activities][:3] == [
        ("search", {"kind": "thinking", "label": "Thinking"}),
        ("search", {"kind": "using_tool", "label": "Using tool"}),
        (
            "search",
            {"kind": "observing", "label": "Observing tool result"},
        ),
    ]
    assert "private query" not in str(activities)
    assert "private result" not in str(activities)


def test_run_research_pipeline_collects_streamed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_assistant.pipelines import pipeline

    async def fake_stream(
        topic: str, dependencies: Any = None, cancellation_event: Any = None
    ):
        assert topic == "topic"
        yield pipeline.PipelineEvent(
            type="run.completed",
            agent=None,
            payload={
                "result": {
                    "search_results": "Search",
                    "scraped_content": "Read",
                    "report": "Report",
                    "feedback": "Critique",
                }
            },
        )

    monkeypatch.setattr(pipeline, "stream_research_pipeline", fake_stream)

    assert pipeline.run_research_pipeline("topic") == {
        "search_results": "Search",
        "scraped_content": "Read",
        "report": "Report",
        "feedback": "Critique",
    }
