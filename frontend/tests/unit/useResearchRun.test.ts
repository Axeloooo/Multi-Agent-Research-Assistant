import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  type EventSourceLike,
  type RunEvent,
  type RunSnapshot,
  initialRunState,
  runReducer,
  useResearchRun
} from "../../src/useResearchRun";

const snapshot: RunSnapshot = {
  run_id: "run-1",
  latest_event_id: 7,
  topic: "energy storage",
  status: "running",
  agents: { search: "running", reader: "pending", writer: "pending", critic: "pending" },
  summaries: { search: "Existing summary", reader: "", writer: "", critic: "" },
  activities: { search: null, reader: null, writer: null, critic: null },
  report: "Existing report",
  critique: "",
  error: null
};

class FakeEventSource implements EventSourceLike {
  listeners = new Map<string, (event: MessageEvent) => void>();
  close = vi.fn();
  onerror: ((event: Event) => void) | null = null;
  onopen: ((event: Event) => void) | null = null;

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.set(type, listener);
  }

  emit(type: string, event: RunEvent) {
    this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(event) }));
  }
}

function mockRunRequests(initialSnapshot: RunSnapshot = snapshot, reconnectSnapshot?: RunSnapshot) {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        run_id: "run-1",
        status_url: "/api/runs/run-1",
        events_url: "/api/runs/run-1/events"
      })
    })
    .mockResolvedValueOnce({ ok: true, json: async () => initialSnapshot });
  if (reconnectSnapshot) {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => reconnectSnapshot });
  }
  vi.stubGlobal("fetch", fetchMock);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("runReducer", () => {
  it("ignores duplicate events and applies report deltas in order", () => {
    const running = runReducer(initialRunState, {
      type: "snapshot",
      snapshot: {
        run_id: "run-1",
        latest_event_id: 0,
        topic: "energy storage",
        status: "running",
        agents: { search: "running", reader: "pending", writer: "pending", critic: "pending" },
        summaries: { search: "", reader: "", writer: "", critic: "" },
        activities: { search: null, reader: null, writer: null, critic: null },
        report: "",
        critique: "",
        error: null
      }
    });

    const updated = runReducer(running, {
      type: "event",
      event: {
        id: 2,
        type: "agent.activity",
        agent: "search",
        payload: { kind: "using_tool", label: "Using tool" }
      }
    });
    const report = runReducer(updated, {
      type: "event",
      event: {
        id: 3,
        type: "report.delta",
        agent: "writer",
        payload: { delta: "First finding." }
      }
    });
    const duplicate = runReducer(report, {
      type: "event",
      event: {
        id: 3,
        type: "report.delta",
        agent: "writer",
        payload: { delta: "First finding." }
      }
    });

    expect(duplicate.snapshot?.report).toBe("First finding.");
    expect(duplicate.snapshot?.activities.search).toEqual({
      kind: "using_tool",
      label: "Using tool"
    });
    expect(duplicate.lastEventId).toBe(3);
  });

  it("resumes after the latest event represented by a snapshot", () => {
    const state = runReducer(initialRunState, { type: "snapshot", snapshot });

    expect(state.lastEventId).toBe(7);
  });

  it("does not replace newer event state with a stale reconnect snapshot", () => {
    const running = runReducer(initialRunState, { type: "snapshot", snapshot });
    const completed = runReducer(running, {
      type: "event",
      event: { id: 8, type: "run.completed", agent: null, payload: {} }
    });

    const stale = runReducer(completed, {
      type: "snapshot",
      snapshot: { ...snapshot, status: "running", latest_event_id: 7 }
    });

    expect(stale.snapshot?.status).toBe("completed");
    expect(stale.lastEventId).toBe(8);
  });
});

describe("useResearchRun", () => {
  it("opens the event stream after the snapshot cursor", async () => {
    mockRunRequests();
    const source = new FakeEventSource();
    const factory = vi.fn(() => source);
    const { result } = renderHook(() => useResearchRun(factory));

    await act(async () => {
      await result.current.start("energy storage");
    });

    expect(factory).toHaveBeenCalledWith("/api/runs/run-1/events?last_event_id=7");
  });

  it.each(["run.completed", "run.failed", "run.cancelled"])(
    "closes the event stream after %s",
    async (eventType) => {
      mockRunRequests();
      const source = new FakeEventSource();
      const { result } = renderHook(() => useResearchRun(() => source));

      await act(async () => {
        await result.current.start("energy storage");
      });
      act(() => {
        source.emit(eventType, {
          id: 8,
          type: eventType,
          agent: null,
          payload: eventType === "run.failed" ? { message: "Safe failure" } : {}
        });
      });

      expect(source.close).toHaveBeenCalledTimes(1);
    }
  );

  it("does not open an event stream for a terminal initial snapshot", async () => {
    mockRunRequests({ ...snapshot, status: "completed", latest_event_id: 8 });
    const factory = vi.fn(() => new FakeEventSource());
    const { result } = renderHook(() => useResearchRun(factory));

    await act(async () => {
      await result.current.start("energy storage");
    });

    expect(factory).not.toHaveBeenCalled();
  });

  it("closes the event stream when reconnect recovery is terminal", async () => {
    mockRunRequests(snapshot, { ...snapshot, status: "completed", latest_event_id: 8 });
    const source = new FakeEventSource();
    const { result } = renderHook(() => useResearchRun(() => source));

    await act(async () => {
      await result.current.start("energy storage");
    });
    act(() => source.onopen?.(new Event("open")));
    act(() => source.onopen?.(new Event("open")));

    await waitFor(() => expect(source.close).toHaveBeenCalledTimes(1));
  });
});
