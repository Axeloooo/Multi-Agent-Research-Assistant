"""FastAPI application for starting and observing research runs."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from backend.src.api.registry import (
    PipelineFactory,
    RunRegistry,
    TERMINAL_STATUSES,
)
from backend.src.pipelines.events import PipelineEvent
from backend.src.pipelines.pipeline import stream_research_pipeline


class StartRunRequest(BaseModel):
    """Validated request body for a new research run."""

    topic: str

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        topic = value.strip()
        if not topic:
            raise ValueError("Topic cannot be empty.")
        if len(topic) > 1000:
            raise ValueError("Topic must be 1000 characters or fewer.")
        return topic


def _default_pipeline(
    topic: str, cancellation_event: asyncio.Event
) -> AsyncIterator[PipelineEvent]:
    return stream_research_pipeline(topic, cancellation_event=cancellation_event)


def _sse_frame(event: dict[str, object]) -> str:
    payload = json.dumps(event, separators=(",", ":"))
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n"


def create_app(pipeline_factory: PipelineFactory = _default_pipeline) -> FastAPI:
    """Create a process-local API application with one active research run."""
    registry = RunRegistry(pipeline_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await registry.shutdown()

    app = FastAPI(title="Multi-Agent Research Assistant", lifespan=lifespan)

    @app.post("/api/runs", status_code=202)
    async def start_run(payload: StartRunRequest) -> JSONResponse:
        record = await registry.enqueue(payload.topic)
        return JSONResponse(
            status_code=202,
            content={
                "run_id": record.run_id,
                "status": record.status,
                "status_url": f"/api/runs/{record.run_id}",
                "events_url": f"/api/runs/{record.run_id}/events",
            },
        )

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, object]:
        try:
            return registry.snapshot(run_id)
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="Research run not found."
            ) from error

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(run_id: str, request: Request) -> StreamingResponse:
        try:
            registry.get(run_id)
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="Research run not found."
            ) from error
        try:
            last_event_id = int(request.headers.get("Last-Event-ID", "0"))
        except ValueError:
            last_event_id = 0

        async def event_stream() -> AsyncIterator[str]:
            cursor = max(last_event_id, 0)
            while True:
                if await request.is_disconnected():
                    return
                try:
                    events = await registry.wait_for_events(run_id, cursor)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                for event in events:
                    cursor = int(event["id"])
                    yield _sse_frame(event)
                if registry.get(run_id).status in TERMINAL_STATUSES:
                    return

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.delete("/api/runs/{run_id}")
    async def cancel_run(run_id: str) -> dict[str, object]:
        try:
            record = await registry.cancel(run_id)
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="Research run not found."
            ) from error
        return registry.snapshot(record.run_id)

    @app.get("/api/runs/{run_id}/downloads/report.md")
    async def download_markdown(run_id: str) -> PlainTextResponse:
        snapshot = _completed_snapshot(registry, run_id)
        document = (
            f"# Research report: {snapshot['topic']}\n\n{snapshot['report']}\n\n"
            f"## Critique\n\n{snapshot['critique']}\n"
        )
        return PlainTextResponse(
            document,
            headers={"Content-Disposition": "attachment; filename=research-report.md"},
        )

    @app.get("/api/runs/{run_id}/downloads/result.json")
    async def download_json(run_id: str) -> JSONResponse:
        return JSONResponse(_completed_snapshot(registry, run_id))

    frontend_dist = Path(__file__).parents[4] / "frontend/dist"
    if frontend_dist.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def _completed_snapshot(registry: RunRegistry, run_id: str) -> dict[str, object]:
    try:
        snapshot = registry.snapshot(run_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Research run not found."
        ) from error
    if snapshot["status"] != "completed":
        raise HTTPException(status_code=409, detail="Research run is not complete.")
    return snapshot
