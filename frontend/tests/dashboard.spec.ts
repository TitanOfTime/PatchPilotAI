import { test, expect } from "@playwright/test";

test("all six workspace views render with accessible navigation", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A clear path from issue to fix." }),
  ).toBeVisible();
  for (const name of [
    "Repositories",
    "Code intelligence",
    "Agent workspace",
    "Evaluations",
    "Settings",
  ]) {
    await page
      .getByRole("navigation")
      .getByRole("button", { name, exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  }
  await expect(page.getByText("Google Gemini", { exact: true })).toBeVisible();
  await expect(
    page.getByText("PostgreSQL + pgvector", { exact: true }),
  ).toBeVisible();
});

test("repository onboarding rejects unsafe hosts and recovers", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Repositories", exact: true })
    .click();
  await page
    .getByLabel("GitHub repository URL")
    .fill("https://attacker.invalid/owner/repo");
  await page.getByRole("button", { name: "Connect & index" }).click();
  await expect(page.locator('.alert[role="alert"]')).toContainText(
    "https://github.com/owner/repository",
  );
  await page.getByRole("button", { name: "Dismiss error" }).click();
  await expect(page.locator('.alert[role="alert"]')).toHaveCount(0);
});

test("indexed Banking App search renders real revision citations", async ({
  page,
  request,
}) => {
  const response = await request.get("http://127.0.0.1:8000/api/repositories");
  expect(response.ok()).toBeTruthy();
  const repos = await response.json();
  const banking = repos.find(
    (r: { name: string; status: string }) =>
      r.name === "TitanOfTime/TestBankingApp" && r.status === "ready",
  );
  test.skip(
    !banking,
    "Requires indexed Banking App; no fixture API data is substituted",
  );
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Code intelligence", exact: true })
    .click();
  await page.getByLabel("Active repository").selectOption(banking.id);
  await page.getByRole("button", { name: "Search only", exact: true }).click();
  await page
    .getByLabel("Question about the repository")
    .fill("Idempotency-Key duplicate requests");
  await page.getByRole("button", { name: "Ask repository" }).click();
  await expect(
    page.getByRole("heading", { name: "Retrieved evidence" }),
  ).toBeVisible({ timeout: 60000 });
  const evidence = page
    .locator("details.evidence")
    .filter({ hasText: "IdempotencyFilter.java" })
    .first();
  await expect(evidence).toBeVisible();
  await evidence.locator("summary").click();
  const sourceLink = evidence.getByRole("link", { name: "View source" });
  await expect(sourceLink).toHaveAttribute(
    "href",
    new RegExp("/blob/" + banking.sha + "/"),
  );
  await expect(evidence.locator("pre")).toContainText("Idempotency");
});

test("desktop and phone layouts remain within viewport and theme works", async ({
  page,
}) => {
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Local environment connected", { exact: true })).toBeAttached();
    await page.screenshot({ path: `../docs/screenshots/overview-${viewport.width}.png`, fullPage: true });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBeTruthy();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Settings", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Environment diagnostics" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBeTruthy();
  }
  await page.getByRole("button", { name: "Toggle color theme" }).click();
  await expect(page.locator(".app-shell")).toHaveClass(/dark/);
});

test("review dialog describes exact operation and cancel preserves checkpoint", async ({
  page,
  request,
}) => {
  const response = await request.get("http://127.0.0.1:8000/api/agents/runs");
  expect(response.ok()).toBeTruthy();
  const runs = await response.json();
  const waiting = runs.find(
    (r: { status: string }) => r.status === "awaiting_review",
  );
  test.skip(!waiting, "Requires a genuine awaiting-review investigation");
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Agent workspace", exact: true })
    .click();
  await page
    .locator(".previous-runs")
    .getByRole("button")
    .filter({ hasText: waiting.data.issue })
    .first()
    .click();
  await page
    .getByRole("button", { name: "Approve patch", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText(
    "Test execution and remote publishing require their own approval",
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  const after = await (
    await request.get("http://127.0.0.1:8000/api/agents/runs/" + waiting.id)
  ).json();
  expect(after.status).toBe("awaiting_review");
});
