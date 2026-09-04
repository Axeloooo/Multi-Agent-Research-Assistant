import { expect, test } from "@playwright/test";

test("streams a deterministic research result through the command center", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Research topic").fill("grid storage");
  await page.getByRole("button", { name: "Start research" }).click();

  await expect(page.getByText("Agent progress")).toBeVisible();
  await expect(page.getByRole("status", { name: "Thinking" })).toBeVisible();
  await expect(page.getByText("Grid storage research brief")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download Markdown" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download JSON" })).toBeVisible();
});
