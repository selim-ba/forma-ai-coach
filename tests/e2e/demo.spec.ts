import { expect, test, type Page } from "@playwright/test";

/**
 * The 60-second demo script from the README, at the iPhone 13 viewport,
 * using the deterministic mock coach (COACH_MODE=mock, set in playwright.config.ts).
 */

async function ready(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  await expect(page.getByTestId("app")).toHaveAttribute("data-avatar", "ready");
  return errors;
}

async function ask(page: Page, text: string) {
  await page.getByTestId("coach-input").fill(text);
  await page.getByTestId("coach-send").click();
  await expect(page.getByTestId("coach-send")).toBeDisabled(); // input cleared
  await expect(page.locator('[aria-label="Coach is typing"]')).toHaveCount(0);
}

test("fits the iPhone 13 viewport without page scroll", async ({ page }) => {
  await ready(page);
  const { scrollH, innerH, scrollW, innerW } = await page.evaluate(() => ({
    scrollH: document.documentElement.scrollHeight,
    innerH: window.innerHeight,
    scrollW: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
  }));
  expect(scrollH).toBeLessThanOrEqual(innerH);
  expect(scrollW).toBeLessThanOrEqual(innerW);
  const canvas = await page.getByTestId("app").locator("canvas").boundingBox();
  expect(canvas!.height / innerH).toBeGreaterThan(0.38);
});

test("manual controls drive the scene", async ({ page }) => {
  const errors = await ready(page);
  const app = page.getByTestId("app");

  await page.getByTestId("play-toggle").click();
  await expect(app).toHaveAttribute("data-playing", "true");
  await page.getByTestId("view-side").click();
  await expect(app).toHaveAttribute("data-view", "side");
  await page.getByTestId("speed-0.5").click();
  await expect(app).toHaveAttribute("data-speed", "0.5");
  await page.getByTestId("phase-bottom").click();
  await expect(app).toHaveAttribute("data-phase", "bottom");
  await expect(app).toHaveAttribute("data-playing", "false");

  await page.getByTestId("exercise-biceps_curl").click();
  await expect(app).toHaveAttribute("data-exercise", "biceps_curl");
  await expect(page.getByTestId("phase-bottom")).toBeDisabled();
  await expect(page.getByTestId("phase-top")).toBeEnabled();
  await page.getByTestId("replay").click();
  await expect(app).toHaveAttribute("data-playing", "true");

  expect(errors).toEqual([]);
});

test("60-second demo script via the coach executes each command once", async ({ page }) => {
  const errors = await ready(page);
  const app = page.getByTestId("app");

  await ask(page, "Show me a beginner squat from the side.");
  await expect(app).toHaveAttribute("data-exercise", "squat");
  await expect(app).toHaveAttribute("data-view", "side");
  await expect(app).toHaveAttribute("data-playing", "true");

  await ask(page, "Slow it down and pause at the bottom.");
  await expect(app).toHaveAttribute("data-speed", "0.5");
  await expect(app).toHaveAttribute("data-phase", "bottom");
  await expect(app).toHaveAttribute("data-playing", "false");

  await ask(page, "What should I pay attention to?");
  await expect(page.getByTestId("message-list").locator('[data-role="assistant"]').last()).toContainText("knees");

  await ask(page, "Switch to a biceps curl, rotate and replay.");
  await expect(app).toHaveAttribute("data-exercise", "biceps_curl");
  await expect(app).toHaveAttribute("data-playing", "true");

  // Exactly-once: the log holds one entry per coach command (3 + 3 + 0 + 4).
  await page.getByTestId("tab-log").click();
  await expect(page.getByTestId("action-log").locator('[data-source="coach"]')).toHaveCount(10);
  await page.screenshot({ path: "test-results/demo-final.png" });
  expect(errors).toEqual([]);
});

test("coach failure keeps manual controls working", async ({ page }) => {
  await page.route("**/api/coach", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ error: "coach_failed", message: "The coach had trouble answering. The manual controls still work.", requestId: "x" }) })
      : route.continue(),
  );
  await ready(page);
  await ask(page, "Show a squat");
  await expect(page.getByTestId("message-list")).toContainText("manual controls still work");
  await page.getByTestId("play-toggle").click();
  await expect(page.getByTestId("app")).toHaveAttribute("data-playing", "true");
});

test("avatar load failure shows a usable fallback", async ({ page }) => {
  await page.route("**/models/*.glb", (route) => route.abort());
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("couldn't load");
  await page.getByTestId("play-toggle").click();
  await expect(page.getByTestId("app")).toHaveAttribute("data-playing", "true");
});
