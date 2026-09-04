"""Research-pipeline sequencing and safe streaming events."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.pipelines.events import AgentName, PipelineEvent, PipelineResult

SearchStage = Callable[[str], Awaitable[str]]
ReaderStage = Callable[[str, str], Awaitable[str]]
WriterStage = Callable[[str, str], AsyncIterator[str]]
CriticStage = Callable[[str], AsyncIterator[str]]
AGENTS: tuple[AgentName, ...] = ("search", "reader", "writer", "critic")


class PipelineCancelled(Exception):
    """Raised internally when a caller requests cooperative cancellation."""


@dataclass(frozen=True)
class PipelineDependencies:
    """Stage runners injected by tests or supplied by the default application."""

    search: SearchStage
    reader: ReaderStage
    writer: WriterStage
    critic: CriticStage


def _message_text(message: Any) -> str:
    """Return textual LangChain message content without provider metadata."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") in {"text", "text-delta"}
        )
    return str(content)


def _safe_summary(value: str) -> str:
    """Bound browser-facing stage output while retaining useful text."""
    return " ".join(value.split())[:1200]


def _status(agent: AgentName, status: str) -> PipelineEvent:
    return PipelineEvent(
        type="agent.status",
        agent=agent,
        payload={"status": status},
    )


def _default_dependencies() -> PipelineDependencies:
    """Create production stage runners lazily to avoid credential work on import."""
    from src.agents.agents import (
        build_critic_chain,
        build_reader_agent,
        build_search_agent,
        build_writer_chain,
    )

    async def search(topic: str) -> str:
        agent = build_search_agent()
        result = await asyncio.to_thread(
            agent.invoke,
            {
                "messages": [
                    ("user", f"Find recent, reliable information about: {topic}")
                ]
            },
        )
        return _message_text(result["messages"][-1])

    async def reader(topic: str, search_results: str) -> str:
        agent = build_reader_agent()
        prompt = (
            "Based on these search results about "
            f"'{topic}', scrape the most relevant URL for deeper content.\n\n"
            f"Search Results:\n{search_results}"
        )
        result = await asyncio.to_thread(
            agent.invoke,
            {
                "messages": [
                    (
                        "user",
                        prompt,
                    )
                ]
            },
        )
        return _message_text(result["messages"][-1])

    async def writer(topic: str, research: str) -> AsyncIterator[str]:
        chain = build_writer_chain()
        async for chunk in chain.astream({"topic": topic, "research": research}):
            yield str(chunk)

    async def critic(report: str) -> AsyncIterator[str]:
        chain = build_critic_chain()
        async for chunk in chain.astream({"report": report}):
            yield str(chunk)

    return PipelineDependencies(
        search=search, reader=reader, writer=writer, critic=critic
    )


def _raise_if_cancelled(cancellation_event: asyncio.Event | None) -> None:
    if cancellation_event is not None and cancellation_event.is_set():
        raise PipelineCancelled


async def stream_research_pipeline(
    topic: str,
    dependencies: PipelineDependencies | None = None,
    cancellation_event: asyncio.Event | None = None,
) -> AsyncIterator[PipelineEvent]:
    """Run Search, Reader, Writer, and Critic while emitting safe events."""
    stages = dependencies or _default_dependencies()
    current_agent: AgentName | None = None
    result: PipelineResult = {
        "search_results": "",
        "scraped_content": "",
        "report": "",
        "feedback": "",
    }

    try:
        current_agent = "search"
        yield _status(current_agent, "running")
        result["search_results"] = await stages.search(topic)
        _raise_if_cancelled(cancellation_event)
        yield PipelineEvent(
            type="agent.output.delta",
            agent=current_agent,
            payload={"delta": _safe_summary(result["search_results"])},
        )
        yield _status(current_agent, "completed")

        current_agent = "reader"
        yield _status(current_agent, "running")
        result["scraped_content"] = await stages.reader(topic, result["search_results"])
        _raise_if_cancelled(cancellation_event)
        yield PipelineEvent(
            type="agent.output.delta",
            agent=current_agent,
            payload={"delta": _safe_summary(result["scraped_content"])},
        )
        yield _status(current_agent, "completed")

        current_agent = "writer"
        yield _status(current_agent, "running")
        research = (
            f"SEARCH RESULTS:\n{result['search_results']}\n\n"
            f"DETAILED SCRAPED CONTENT:\n{result['scraped_content']}"
        )
        async for delta in stages.writer(topic, research):
            _raise_if_cancelled(cancellation_event)
            result["report"] += delta
            yield PipelineEvent(
                type="report.delta", agent=current_agent, payload={"delta": delta}
            )
        yield _status(current_agent, "completed")

        current_agent = "critic"
        yield _status(current_agent, "running")
        async for delta in stages.critic(result["report"]):
            _raise_if_cancelled(cancellation_event)
            result["feedback"] += delta
            yield PipelineEvent(
                type="critique.delta", agent=current_agent, payload={"delta": delta}
            )
        yield _status(current_agent, "completed")
        yield PipelineEvent(
            type="run.completed", agent=None, payload={"result": result}
        )
    except PipelineCancelled:
        if current_agent is not None:
            yield _status(current_agent, "cancelled")
            for agent in AGENTS[AGENTS.index(current_agent) + 1 :]:
                yield _status(agent, "skipped")
        yield PipelineEvent(type="run.cancelled", agent=None, payload={})
    except Exception:
        if current_agent is not None:
            yield _status(current_agent, "failed")
            for agent in AGENTS[AGENTS.index(current_agent) + 1 :]:
                yield _status(agent, "skipped")
        yield PipelineEvent(
            type="run.failed",
            agent=current_agent,
            payload={"message": "Research run failed. Please try again."},
        )


def run_research_pipeline(
    topic: str,
    dependencies: PipelineDependencies | None = None,
) -> PipelineResult:
    """Collect the async stream for existing command-line callers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "run_research_pipeline cannot run inside an event loop; "
            "use stream_research_pipeline instead."
        )

    async def collect() -> PipelineResult:
        async for event in stream_research_pipeline(topic, dependencies):
            if event.type == "run.completed":
                return event.payload["result"]  # type: ignore[return-value]
            if event.type == "run.failed":
                raise RuntimeError(str(event.payload["message"]))
            if event.type == "run.cancelled":
                raise RuntimeError("Research run cancelled.")
        raise RuntimeError("Research run finished without a result.")

    return asyncio.run(collect())
