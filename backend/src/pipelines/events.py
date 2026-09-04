"""Typed, provider-neutral events emitted by the research pipeline."""

from dataclasses import dataclass
from typing import Literal, TypedDict

AgentName = Literal["search", "reader", "writer", "critic"]
AgentStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "skipped",
]
ActivityKind = Literal["thinking", "using_tool", "observing", "streaming"]
EventType = Literal[
    "agent.status",
    "agent.activity",
    "agent.output.delta",
    "report.delta",
    "critique.delta",
    "run.completed",
    "run.failed",
    "run.cancelled",
]


class PipelineResult(TypedDict):
    """The legacy final result returned by the synchronous pipeline."""

    search_results: str
    scraped_content: str
    report: str
    feedback: str


@dataclass(frozen=True)
class PipelineEvent:
    """A safe domain event suitable for delivery to the HTTP layer."""

    type: EventType
    agent: AgentName | None
    payload: dict[str, object]
