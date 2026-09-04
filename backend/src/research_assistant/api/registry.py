"""In-memory, single-worker registry for research runs and safe SSE events."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from research_assistant.pipelines.events import AgentName, AgentStatus, PipelineEvent

RunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
PipelineFactory = Callable[[str, asyncio.Event], AsyncIterator[PipelineEvent]]
AGENTS: tuple[AgentName, ...] = ("search", "reader", "writer", "critic")
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
MAX_TERMINAL_RUNS = 20


@dataclass
class RunRecord:
    """Process-local state for a single research run."""

    run_id: str
    topic: str
    status: RunStatus = "queued"
    agents: dict[AgentName, AgentStatus] = field(
        default_factory=lambda: {agent: "pending" for agent in AGENTS}
    )
    summaries: dict[AgentName, str] = field(
        default_factory=lambda: {agent: "" for agent in AGENTS}
    )
    report: str = ""
    critique: str = ""
    error: str | None = None
    events: list[dict[str, object]] = field(default_factory=list)
    cancellation_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None


class RunRegistry:
    """Serialize runs, keep safe event history, and expose status snapshots."""

    def __init__(self, pipeline_factory: PipelineFactory) -> None:
        self._pipeline_factory = pipeline_factory
        self._records: dict[str, RunRecord] = {}
        self._queue: deque[str] = deque()
        self._active_run_id: str | None = None
        self._condition = asyncio.Condition()

    async def enqueue(self, topic: str) -> RunRecord:
        """Create a queued run and start it if the single worker is free."""
        record = RunRecord(run_id=str(uuid4()), topic=topic)
        self._records[record.run_id] = record
        self._queue.append(record.run_id)
        await self._start_next()
        return record

    def get(self, run_id: str) -> RunRecord:
        """Look up a retained run or raise ``KeyError`` for a 404 response."""
        try:
            return self._records[run_id]
        except KeyError as error:
            raise KeyError(run_id) from error

    async def cancel(self, run_id: str) -> RunRecord:
        """Cancel a queued or active run. Repeated requests are idempotent."""
        record = self.get(run_id)
        if record.status in TERMINAL_STATUSES:
            return record

        record.cancellation_event.set()
        if record.status == "queued":
            with suppress(ValueError):
                self._queue.remove(run_id)
            await self._finish(record, "cancelled")
            return record

        if record.task is not None:
            record.task.cancel()
        await self._finish(record, "cancelled")
        return record

    async def shutdown(self) -> None:
        """Stop background work during application shutdown."""
        tasks = [
            record.task
            for record in self._records.values()
            if record.task is not None and not record.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def wait_for_events(
        self, run_id: str, last_event_id: int
    ) -> list[dict[str, object]]:
        """Wait for new events, returning quickly when a run is terminal."""
        while True:
            record = self.get(run_id)
            events = [event for event in record.events if event["id"] > last_event_id]
            if events or record.status in TERMINAL_STATUSES:
                return events
            async with self._condition:
                await asyncio.wait_for(self._condition.wait(), timeout=15)

    def snapshot(self, run_id: str) -> dict[str, object]:
        """Return the UI-safe representation of a run."""
        record = self.get(run_id)
        return {
            "run_id": record.run_id,
            "topic": record.topic,
            "status": record.status,
            "agents": record.agents,
            "summaries": record.summaries,
            "report": record.report,
            "critique": record.critique,
            "error": record.error,
        }

    async def _start_next(self) -> None:
        if self._active_run_id is not None:
            return
        while self._queue:
            run_id = self._queue.popleft()
            record = self._records.get(run_id)
            if record is None or record.status != "queued":
                continue
            self._active_run_id = run_id
            record.status = "running"
            await self._publish(record, "run.started", None, {})
            record.task = asyncio.create_task(self._execute(record))
            return

    async def _execute(self, record: RunRecord) -> None:
        try:
            async for event in self._pipeline_factory(
                record.topic, record.cancellation_event
            ):
                if record.status in TERMINAL_STATUSES:
                    return
                await self._apply_pipeline_event(record, event)
                if record.status in TERMINAL_STATUSES:
                    return
            if record.status not in TERMINAL_STATUSES:
                await self._finish(
                    record,
                    "failed",
                    "Research run failed. Please try again.",
                )
        except asyncio.CancelledError:
            return
        except Exception:
            await self._finish(
                record, "failed", "Research run failed. Please try again."
            )

    async def _apply_pipeline_event(
        self, record: RunRecord, event: PipelineEvent
    ) -> None:
        if event.type == "agent.status" and event.agent is not None:
            status = event.payload.get("status")
            if status in {
                "pending",
                "running",
                "completed",
                "failed",
                "cancelled",
                "skipped",
            }:
                record.agents[event.agent] = status
                await self._publish(record, event.type, event.agent, {"status": status})
            return

        if event.type == "agent.output.delta" and event.agent is not None:
            delta = self._safe_text(event.payload.get("delta"), 1200)
            record.summaries[event.agent] = self._safe_text(
                record.summaries[event.agent] + delta, 2400
            )
            await self._publish(record, event.type, event.agent, {"delta": delta})
            return

        if event.type == "report.delta":
            delta = self._safe_text(event.payload.get("delta"), 10000)
            record.report += delta
            await self._publish(record, event.type, event.agent, {"delta": delta})
            return

        if event.type == "critique.delta":
            delta = self._safe_text(event.payload.get("delta"), 10000)
            record.critique += delta
            await self._publish(record, event.type, event.agent, {"delta": delta})
            return

        if event.type == "run.completed":
            result = event.payload.get("result")
            if isinstance(result, dict):
                record.summaries["search"] = self._safe_text(
                    result.get("search_results"), 2400
                )
                record.summaries["reader"] = self._safe_text(
                    result.get("scraped_content"), 2400
                )
                record.report = self._safe_text(result.get("report"), 100000)
                record.critique = self._safe_text(result.get("feedback"), 100000)
            await self._finish(record, "completed")
            return

        if event.type == "run.cancelled":
            await self._finish(record, "cancelled")
            return

        if event.type == "run.failed":
            await self._finish(
                record, "failed", "Research run failed. Please try again."
            )

    async def _finish(
        self, record: RunRecord, status: RunStatus, error: str | None = None
    ) -> None:
        if record.status in TERMINAL_STATUSES:
            return
        record.status = status
        record.error = error
        for agent, agent_status in record.agents.items():
            if agent_status in {"pending", "running"}:
                record.agents[agent] = (
                    "skipped" if status != "cancelled" else "cancelled"
                )
                await self._publish(
                    record,
                    "agent.status",
                    agent,
                    {"status": record.agents[agent]},
                )
        event_type = f"run.{status}"
        payload: dict[str, object] = {"message": error} if error else {}
        await self._publish(record, event_type, None, payload)
        if self._active_run_id == record.run_id:
            self._active_run_id = None
            await self._start_next()
        self._evict_terminal_runs()

    async def _publish(
        self,
        record: RunRecord,
        event_type: str,
        agent: AgentName | None,
        payload: dict[str, object],
    ) -> None:
        event = {
            "id": len(record.events) + 1,
            "run_id": record.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "type": event_type,
            "agent": agent,
            "payload": payload,
        }
        record.events.append(event)
        async with self._condition:
            self._condition.notify_all()

    def _evict_terminal_runs(self) -> None:
        terminal = [
            record
            for record in self._records.values()
            if record.status in TERMINAL_STATUSES
        ]
        if len(terminal) <= MAX_TERMINAL_RUNS:
            return
        terminal.sort(key=lambda record: record.events[-1]["timestamp"])
        for record in terminal[:-MAX_TERMINAL_RUNS]:
            self._records.pop(record.run_id, None)

    @staticmethod
    def _safe_text(value: Any, limit: int) -> str:
        return value[:limit] if isinstance(value, str) else ""
