import type { Preview } from "@storybook/react-vite";

import "../src/styles.css";

const preview: Preview = {
  parameters: {
    backgrounds: {
      default: "command center",
      values: [{ name: "command center", value: "#07111f" }]
    }
  }
};

export default preview;
