"""Offline contract tests for the research run HTTP API."""

import asyncio
import time
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from research_assistant.pipelines.events import PipelineEvent


def _scripted_pipeline(
    topic: str, cancellation_event: asyncio.Event
) -> AsyncIterator[PipelineEvent]:
    async def events() -> AsyncIterator[PipelineEvent]:
        assert topic == "climate policy"
        assert not cancellation_event.is_set()
        yield PipelineEvent(
            type="agent.status", agent="search", payload={"status": "running"}
        )
        yield PipelineEvent(
            type="agent.output.delta",
            agent="search",
            payload={"delta": "A reliable source."},
        )
        yield PipelineEvent(
            type="agent.status", agent="search", payload={"status": "completed"}
        )
        for agent in ("reader", "writer", "critic"):
            yield PipelineEvent(
                type="agent.status", agent=agent, payload={"status": "running"}
            )
            if agent == "writer":
                yield PipelineEvent(
                    type="report.delta", agent=agent, payload={"delta": "Report body"}
                )
            elif agent == "critic":
                yield PipelineEvent(
                    type="critique.delta", agent=agent, payload={"delta": "Looks good"}
                )
            yield PipelineEvent(
                type="agent.status", agent=agent, payload={"status": "completed"}
            )
        yield PipelineEvent(
            type="run.completed",
            agent=None,
            payload={
                "result": {
                    "search_results": "A reliable source.",
                    "scraped_content": "Source details.",
                    "report": "Report body",
                    "feedback": "Looks good",
                }
            },
        )

    return events()


def _client() -> TestClient:
    from research_assistant.api.app import create_app

    return TestClient(create_app(pipeline_factory=_scripted_pipeline))


def _wait_for_terminal(client: TestClient, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        snapshot = response.json()
        if snapshot["status"] in {"completed", "failed", "cancelled"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("research run did not finish")


def test_start_rejects_empty_and_oversized_topics() -> None:
    with _client() as client:
        assert client.post("/api/runs", json={"topic": "   "}).status_code == 422
        assert client.post("/api/runs", json={"topic": "x" * 1001}).status_code == 422


def test_api_streams_replayable_safe_events_and_downloads() -> None:
    with _client() as client:
        created = client.post("/api/runs", json={"topic": "climate policy"})
        assert created.status_code == 202
        run_id = created.json()["run_id"]

        snapshot = _wait_for_terminal(client, run_id)
        assert snapshot["status"] == "completed"
        assert snapshot["agents"]["critic"] == "completed"
        assert snapshot["report"] == "Report body"
        assert snapshot["critique"] == "Looks good"

        events = client.get(f"/api/runs/{run_id}/events")
        assert events.status_code == 200
        assert events.headers["content-type"].startswith("text/event-stream")
        assert "event: run.completed" in events.text
        assert "raw tool" not in events.text

        replay = client.get(
            f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "1"}
        )
        assert "id: 1\nevent:" not in replay.text
        assert "event: run.completed" in replay.text

        markdown = client.get(f"/api/runs/{run_id}/downloads/report.md")
        assert markdown.status_code == 200
        assert "Report body" in markdown.text
        assert "attachment" in markdown.headers["content-disposition"]

        result = client.get(f"/api/runs/{run_id}/downloads/result.json")
        assert result.status_code == 200
        assert result.json()["report"] == "Report body"


def test_api_rejects_download_before_completion() -> None:
    async def pending_pipeline(
        topic: str, cancellation_event: asyncio.Event
    ) -> AsyncIterator[PipelineEvent]:
        yield PipelineEvent(
            type="agent.status", agent="search", payload={"status": "running"}
        )
        await asyncio.Event().wait()

    from research_assistant.api.app import create_app

    with TestClient(create_app(pipeline_factory=pending_pipeline)) as client:
        run_id = client.post("/api/runs", json={"topic": "climate policy"}).json()[
            "run_id"
        ]
        assert client.get(f"/api/runs/{run_id}/downloads/report.md").status_code == 409


def test_cancelling_active_run_starts_the_next_queued_run() -> None:
    async def queued_pipeline(
        topic: str, cancellation_event: asyncio.Event
    ) -> AsyncIterator[PipelineEvent]:
        yield PipelineEvent(
            type="agent.status", agent="search", payload={"status": "running"}
        )
        if topic == "first":
            await asyncio.Event().wait()
        else:
            yield PipelineEvent(
                type="run.completed",
                agent=None,
                payload={
                    "result": {
                        "search_results": "",
                        "scraped_content": "",
                        "report": "Second report",
                        "feedback": "",
                    }
                },
            )

    from research_assistant.api.app import create_app

    with TestClient(create_app(pipeline_factory=queued_pipeline)) as client:
        first_id = client.post("/api/runs", json={"topic": "first"}).json()["run_id"]
        second_id = client.post("/api/runs", json={"topic": "second"}).json()["run_id"]
        assert client.get(f"/api/runs/{second_id}").json()["status"] == "queued"

        cancelled = client.delete(f"/api/runs/{first_id}")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert client.delete(f"/api/runs/{first_id}").json()["status"] == "cancelled"

        assert _wait_for_terminal(client, second_id)["report"] == "Second report"
