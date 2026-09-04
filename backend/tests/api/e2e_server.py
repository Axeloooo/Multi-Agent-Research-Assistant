"""Deterministic local API used exclusively by the browser end-to-end test."""

import asyncio
from collections.abc import AsyncIterator

import uvicorn

from research_assistant.api.app import create_app
from research_assistant.pipelines.events import PipelineEvent


async def fake_pipeline(
    topic: str, cancellation_event: asyncio.Event
) -> AsyncIterator[PipelineEvent]:
    """Stream predictable, credential-free data through the real run API."""
    del cancellation_event
    yield PipelineEvent(
        type="agent.status", agent="search", payload={"status": "running"}
    )
    yield PipelineEvent(
        type="agent.output.delta",
        agent="search",
        payload={"delta": f"Reliable sources for {topic}."},
    )
    yield PipelineEvent(
        type="agent.status", agent="search", payload={"status": "completed"}
    )
    for agent in ("reader", "writer", "critic"):
        yield PipelineEvent(
            type="agent.status", agent=agent, payload={"status": "running"}
        )
        await asyncio.sleep(0.03)
        if agent == "writer":
            yield PipelineEvent(
                type="report.delta",
                agent=agent,
                payload={
                    "delta": (
                        "# Grid storage research brief\n\n"
                        "A safe, deterministic result."
                    )
                },
            )
        elif agent == "critic":
            yield PipelineEvent(
                type="critique.delta",
                agent=agent,
                payload={"delta": "The brief is ready to review."},
            )
        yield PipelineEvent(
            type="agent.status", agent=agent, payload={"status": "completed"}
        )
    yield PipelineEvent(
        type="run.completed",
        agent=None,
        payload={
            "result": {
                "search_results": f"Reliable sources for {topic}.",
                "scraped_content": "Deterministic source context.",
                "report": (
                    "# Grid storage research brief\n\nA safe, deterministic result."
                ),
                "feedback": "The brief is ready to review.",
            }
        },
    )


app = create_app(pipeline_factory=fake_pipeline)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
