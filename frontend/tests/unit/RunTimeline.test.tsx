import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunTimeline } from "../../src/components/RunTimeline";

describe("RunTimeline", () => {
  it("exposes safe stage status and an expandable summary", () => {
    render(
      <RunTimeline
        agents={{ search: "completed", reader: "running", writer: "pending", critic: "pending" }}
        summaries={{
          search: "Three trusted sources found.",
          reader: "",
          writer: "",
          critic: ""
        }}
        activities={{
          search: null,
          reader: { kind: "using_tool", label: "Using tool" },
          writer: null,
          critic: null
        }}
      />
    );

    expect(screen.getByText("Search")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("Three trusted sources found.")).toBeInTheDocument();
    expect(screen.getByText("Using tool")).toBeInTheDocument();
  });
});
