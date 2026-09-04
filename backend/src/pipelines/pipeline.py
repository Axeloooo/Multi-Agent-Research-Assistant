"""Research-pipeline sequencing and safe streaming events."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from backend.src.pipelines.events import (
    ActivityKind,
    AgentName,
    PipelineEvent,
    PipelineResult,
)

SearchStage = Callable[[str], Awaitable[str]]
ReaderStage = Callable[[str, str], Awaitable[str]]
WriterStage = Callable[[str, str], AsyncIterator[str]]
CriticStage = Callable[[str], AsyncIterator[str]]
AGENTS: tuple[AgentName, ...] = ("search", "reader", "writer", "critic")


class PipelineCancelled(Exception):
    """Raised internally when a caller requests cooperative cancellation."""


class PipelineStageTimedOut(Exception):
    """Raised when a stage exceeds its bounded runtime."""


@dataclass(frozen=True)
class PipelineTimeouts:
    """Maximum time each agent may occupy a research run, in seconds."""

    search: float = 45
    reader: float = 45
    writer: float = 90
    critic: float = 45


class _ActivityEmitter:
    """Bridge provider lifecycle callbacks into the pipeline event loop."""

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.queue: asyncio.Queue[PipelineEvent] = asyncio.Queue()
        self._lock = Lock()
        self._pending_callbacks = 0

    def publish(self, agent: AgentName, kind: ActivityKind) -> None:
        with self._lock:
            self._pending_callbacks += 1

        def deliver() -> None:
            self.queue.put_nowait(_activity(agent, kind))
            with self._lock:
                self._pending_callbacks -= 1

        self._loop.call_soon_threadsafe(
            deliver,
        )

    def callback(self, agent: AgentName) -> "_ToolActivityCallback":
        return _ToolActivityCallback(self, agent)

    @property
    def has_pending_callbacks(self) -> bool:
        with self._lock:
            return self._pending_callbacks > 0


class _ToolActivityCallback(BaseCallbackHandler):
    """Emit fixed, non-sensitive labels for LangChain tool lifecycle events."""

    def __init__(self, emitter: _ActivityEmitter, agent: AgentName) -> None:
        self._emitter = emitter
        self._agent = agent

    def on_tool_start(self, *args: Any, **kwargs: Any) -> None:
        self._emitter.publish(self._agent, "using_tool")

    def on_tool_end(self, *args: Any, **kwargs: Any) -> None:
        self._emitter.publish(self._agent, "observing")


@dataclass(frozen=True)
class PipelineDependencies:
    """Stage runners injected by tests or supplied by the default application."""

    search: SearchStage
    reader: ReaderStage
    writer: WriterStage
    critic: CriticStage
    activity: _ActivityEmitter | None = None


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


def _activity(agent: AgentName, kind: ActivityKind) -> PipelineEvent:
    labels: dict[ActivityKind, str] = {
        "thinking": "Thinking",
        "using_tool": "Using tool",
        "observing": "Observing tool result",
        "streaming": "Streaming response",
    }
    return PipelineEvent(
        type="agent.activity",
        agent=agent,
        payload={"kind": kind, "label": labels[kind]},
    )


def _default_dependencies() -> PipelineDependencies:
    """Create production stage runners lazily to avoid credential work on import."""
    from backend.src.agents.agents import (
        build_critic_chain,
        build_reader_agent,
        build_search_agent,
        build_writer_chain,
    )

    activity = _ActivityEmitter()

    async def search(topic: str) -> str:
        agent = build_search_agent()
        result = await asyncio.to_thread(
            agent.invoke,
            {
                "messages": [
                    ("user", f"Find recent, reliable information about: {topic}")
                ]
            },
            config={"callbacks": [activity.callback("search")]},
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
            config={"callbacks": [activity.callback("reader")]},
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
        search=search, reader=reader, writer=writer, critic=critic, activity=activity
    )


def _raise_if_cancelled(cancellation_event: asyncio.Event | None) -> None:
    if cancellation_event is not None and cancellation_event.is_set():
        raise PipelineCancelled


async def _stream_stage_activity(
    awaitable: Awaitable[str],
    timeout: float,
    activity: _ActivityEmitter | None,
    result: list[str],
) -> AsyncIterator[PipelineEvent]:
    """Wait for a stage while relaying provider activity and enforcing its deadline."""
    task = asyncio.ensure_future(awaitable)
    activity_task = (
        asyncio.create_task(activity.queue.get()) if activity is not None else None
    )
    deadline = asyncio.get_running_loop().time() + timeout

    try:
        while not task.done():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise PipelineStageTimedOut
            waiters: set[asyncio.Future[Any]] = {task}
            if activity_task is not None:
                waiters.add(activity_task)
            done, _ = await asyncio.wait(
                waiters, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                raise PipelineStageTimedOut
            if activity_task is not None and activity_task in done:
                yield activity_task.result()
                activity_task = asyncio.create_task(activity.queue.get())

        result.append(task.result())
        if activity is not None:
            while activity.has_pending_callbacks:
                await asyncio.sleep(0)
            while not activity.queue.empty():
                yield activity.queue.get_nowait()
    except BaseException:
        task.cancel()
        raise
    finally:
        if activity_task is not None:
            activity_task.cancel()
        if not task.done():
            task.cancel()


async def _bounded_deltas(
    deltas: AsyncIterator[str], timeout: float
) -> AsyncIterator[str]:
    """Yield model output while imposing a total stage deadline."""
    iterator = aiter(deltas)
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise PipelineStageTimedOut
            try:
                yield await asyncio.wait_for(anext(iterator), timeout=remaining)
            except StopAsyncIteration:
                return
    finally:
        await iterator.aclose()


async def stream_research_pipeline(
    topic: str,
    dependencies: PipelineDependencies | None = None,
    cancellation_event: asyncio.Event | None = None,
    timeouts: PipelineTimeouts = PipelineTimeouts(),
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
        yield _activity(current_agent, "thinking")
        search_result: list[str] = []
        async for event in _stream_stage_activity(
            stages.search(topic), timeouts.search, stages.activity, search_result
        ):
            yield event
        result["search_results"] = search_result[0]
        _raise_if_cancelled(cancellation_event)
        yield PipelineEvent(
            type="agent.output.delta",
            agent=current_agent,
            payload={"delta": _safe_summary(result["search_results"])},
        )
        yield _status(current_agent, "completed")

        current_agent = "reader"
        yield _status(current_agent, "running")
        yield _activity(current_agent, "thinking")
        reader_result: list[str] = []
        async for event in _stream_stage_activity(
            stages.reader(topic, result["search_results"]),
            timeouts.reader,
            stages.activity,
            reader_result,
        ):
            yield event
        result["scraped_content"] = reader_result[0]
        _raise_if_cancelled(cancellation_event)
        yield PipelineEvent(
            type="agent.output.delta",
            agent=current_agent,
            payload={"delta": _safe_summary(result["scraped_content"])},
        )
        yield _status(current_agent, "completed")

        current_agent = "writer"
        yield _status(current_agent, "running")
        yield _activity(current_agent, "thinking")
        yield _activity(current_agent, "streaming")
        research = (
            f"SEARCH RESULTS:\n{result['search_results']}\n\n"
            f"DETAILED SCRAPED CONTENT:\n{result['scraped_content']}"
        )
        async for delta in _bounded_deltas(
            stages.writer(topic, research), timeouts.writer
        ):
            _raise_if_cancelled(cancellation_event)
            result["report"] += delta
            yield PipelineEvent(
                type="report.delta", agent=current_agent, payload={"delta": delta}
            )
        yield _status(current_agent, "completed")

        current_agent = "critic"
        yield _status(current_agent, "running")
        yield _activity(current_agent, "thinking")
        yield _activity(current_agent, "streaming")
        async for delta in _bounded_deltas(
            stages.critic(result["report"]), timeouts.critic
        ):
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
