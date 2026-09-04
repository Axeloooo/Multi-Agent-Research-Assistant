import { useCallback, useEffect, useReducer, useRef, useState } from "react";

export type AgentName = "search" | "reader" | "writer" | "critic";
export type AgentStatus = "pending" | "running" | "completed" | "failed" | "cancelled" | "skipped";
export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface RunSnapshot {
  run_id: string;
  topic: string;
  status: RunStatus;
  agents: Record<AgentName, AgentStatus>;
  summaries: Record<AgentName, string>;
  report: string;
  critique: string;
  error: string | null;
}

export interface RunEvent {
  id: number;
  type: string;
  agent: AgentName | null;
  payload: Record<string, unknown>;
}

interface StartResponse {
  run_id: string;
  status_url: string;
  events_url: string;
}

export interface EventSourceLike {
  addEventListener: (type: string, listener: (event: MessageEvent) => void) => void;
  close: () => void;
  onerror: ((event: Event) => void) | null;
  onopen: ((event: Event) => void) | null;
}

export interface RunState {
  snapshot: RunSnapshot | null;
  lastEventId: number;
}

export const initialRunState: RunState = { snapshot: null, lastEventId: 0 };

type RunAction =
  | { type: "snapshot"; snapshot: RunSnapshot }
  | { type: "event"; event: RunEvent }
  | { type: "clear" };

const terminalStatuses = new Set<RunStatus>(["completed", "failed", "cancelled"]);

function textPayload(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

export function runReducer(state: RunState, action: RunAction): RunState {
  if (action.type === "clear") {
    return initialRunState;
  }
  if (action.type === "snapshot") {
    const sameRun = state.snapshot?.run_id === action.snapshot.run_id;
    return { snapshot: action.snapshot, lastEventId: sameRun ? state.lastEventId : 0 };
  }
  if (!state.snapshot || action.event.id <= state.lastEventId) {
    return state;
  }

  const snapshot = {
    ...state.snapshot,
    agents: { ...state.snapshot.agents },
    summaries: { ...state.snapshot.summaries }
  };
  const { agent, payload, type } = action.event;
  if (type === "agent.status" && agent) {
    const status = textPayload(payload, "status") as AgentStatus;
    snapshot.agents[agent] = status;
  } else if (type === "agent.output.delta" && agent) {
    snapshot.summaries[agent] += textPayload(payload, "delta");
  } else if (type === "report.delta") {
    snapshot.report += textPayload(payload, "delta");
  } else if (type === "critique.delta") {
    snapshot.critique += textPayload(payload, "delta");
  } else if (type === "run.completed") {
    snapshot.status = "completed";
  } else if (type === "run.failed") {
    snapshot.status = "failed";
    snapshot.error = textPayload(payload, "message") || "Research run failed. Please try again.";
  } else if (type === "run.cancelled") {
    snapshot.status = "cancelled";
  }
  return { snapshot, lastEventId: action.event.id };
}

function nativeEventSourceFactory(url: string): EventSourceLike {
  return new EventSource(url);
}

async function fetchSnapshot(url: string): Promise<RunSnapshot> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("Unable to load research status.");
  }
  return (await response.json()) as RunSnapshot;
}

export function useResearchRun(
  eventSourceFactory: (url: string) => EventSourceLike = nativeEventSourceFactory
) {
  const [state, dispatch] = useReducer(runReducer, initialRunState);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const sourceRef = useRef<EventSourceLike | null>(null);

  const closeStream = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  const connect = useCallback(
    (start: StartResponse) => {
      let openedOnce = false;
      const source = eventSourceFactory(start.events_url);
      sourceRef.current = source;
      const updateFromEvent = (message: MessageEvent) => {
        try {
          dispatch({ type: "event", event: JSON.parse(message.data) as RunEvent });
        } catch {
          // Ignore malformed event data; a later snapshot recovers the UI.
        }
      };
      for (const eventType of [
        "run.started",
        "agent.status",
        "agent.output.delta",
        "report.delta",
        "critique.delta",
        "run.completed",
        "run.failed",
        "run.cancelled"
      ]) {
        source.addEventListener(eventType, updateFromEvent);
      }
      source.onopen = () => {
        if (openedOnce) {
          void fetchSnapshot(start.status_url)
            .then((snapshot) => dispatch({ type: "snapshot", snapshot }))
            .catch(() => undefined);
        }
        openedOnce = true;
      };
      source.onerror = () => {
        // Native EventSource reconnects automatically and preserves Last-Event-ID.
      };
    },
    [eventSourceFactory]
  );

  const start = useCallback(
    async (topic: string) => {
      setIsSubmitting(true);
      closeStream();
      try {
        const response = await fetch("/api/runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic })
        });
        if (!response.ok) {
          throw new Error("Unable to start research.");
        }
        const created = (await response.json()) as StartResponse;
        const snapshot = await fetchSnapshot(created.status_url);
        dispatch({ type: "snapshot", snapshot });
        connect(created);
      } finally {
        setIsSubmitting(false);
      }
    },
    [closeStream, connect]
  );

  const cancel = useCallback(async () => {
    const runId = state.snapshot?.run_id;
    if (!runId) {
      return;
    }
    const response = await fetch(`/api/runs/${runId}`, { method: "DELETE" });
    if (!response.ok) {
      throw new Error("Unable to cancel research.");
    }
    dispatch({ type: "snapshot", snapshot: (await response.json()) as RunSnapshot });
    closeStream();
  }, [closeStream, state.snapshot?.run_id]);

  useEffect(() => closeStream, [closeStream]);

  return { ...state, isSubmitting, start, cancel, clear: () => dispatch({ type: "clear" }) };
}

export { terminalStatuses };
