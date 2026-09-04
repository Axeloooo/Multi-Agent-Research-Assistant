import { describe, expect, it } from "vitest";

import { initialRunState, runReducer } from "../../src/useResearchRun";

describe("runReducer", () => {
  it("ignores duplicate events and applies report deltas in order", () => {
    const running = runReducer(initialRunState, {
      type: "snapshot",
      snapshot: {
        run_id: "run-1",
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
});
