import type { Meta, StoryObj } from "@storybook/react-vite";

import { RunTimeline } from "./RunTimeline";

const meta = {
  title: "Command Center/RunTimeline",
  component: RunTimeline
} satisfies Meta<typeof RunTimeline>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Active: Story = {
  args: {
    agents: { search: "completed", reader: "completed", writer: "running", critic: "pending" },
    summaries: {
      search: "Three primary sources selected.",
      reader: "Extracted technical and policy context.",
      writer: "",
      critic: ""
    },
    activities: {
      search: null,
      reader: null,
      writer: { kind: "streaming", label: "Streaming response" },
      critic: null
    }
  }
};
