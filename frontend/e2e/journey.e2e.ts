import { expect, test, type Page } from "@playwright/test";

/**
 * The PRD's core journey, end to end, as one user (serial: each step builds on the last):
 * register → onboarding → task → event → reminder (+ real alarm) → habit → book & reading session → workout →
 * dashboard → notification preferences → another user cannot see any of it.
 */
test.describe.configure({ mode: "serial" });

const stamp = Date.now();
const user = { email: `e2e-${stamp}@daywell.test`, password: "E2e-calm-mornings-2026", name: "Wanjiru" };
let page: Page;
let taskId = 0;

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
});

test("1. register a new user", async () => {
  await page.goto("/register");
  await page.getByLabel("What should we call you?").fill(user.name);
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/welcome$/);
  await expect(page.getByRole("heading", { name: `Hello, ${user.name}! Welcome to DayWell.` })).toBeVisible();
});

test("2. complete onboarding", async () => {
  await page.getByRole("button", { name: "Let's begin" }).click();
  await page.getByRole("button", { name: "Reading more" }).click();
  await page.getByRole("button", { name: "Exercising regularly" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("switch", { name: "Reading" })).toHaveAttribute("aria-checked", "true");
  for (let i = 0; i < 5; i++) await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Stretch" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Show my day" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(user.name);
});

test("3. create a task with quick add", async () => {
  await page.getByRole("button", { name: "Quick add" }).first().click();
  await page.getByLabel("What do you need to do?").fill("Call the supplier tomorrow at 10 am and remind me 15 minutes before");
  await expect(page.getByText("Reminder: 15 min before")).toBeVisible();
  const created = page.waitForResponse((r) => r.url().endsWith("/api/v1/tasks/") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Add task" }).click();
  taskId = (await (await created).json()).id;
  await page.goto("/tasks?view=upcoming");
  await expect(page.getByText("Call the supplier")).toBeVisible();
});

test("4. create a calendar event", async () => {
  await page.goto("/calendar");
  await page.getByRole("button", { name: "New event" }).click();
  await page.getByLabel("Title").fill("Book club");
  await page.getByLabel("Start time").fill("19:00");
  await page.getByLabel("End time").fill("20:00");
  await page.getByRole("button", { name: "Add event" }).click();
  await expect(page.locator(".fc-event", { hasText: "Book club" }).first()).toBeVisible();
});

test("5. configure a reminder and receive a real alarm", async () => {
  await page.goto("/reminders");
  await page.getByRole("button", { name: "New reminder" }).click();
  await page.getByLabel("Title").fill("Take vitamins");
  await page.getByLabel("Time").fill("08:30");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Take vitamins")).toBeVisible();
  // Real pipeline: the test alarm is dispatched by the server, then picked up by the in-app alarm poller.
  await page.goto("/settings/notifications");
  await page.getByRole("button", { name: "Test alarm now" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await expect(dialog).toContainText("Test alarm");
  await dialog.getByRole("button", { name: "Dismiss" }).click();
  await expect(dialog).toBeHidden();
  await page.goto("/notifications");
  await expect(page.getByText("Test alarm").first()).toBeVisible();
  await expect(page.getByText("Dismissed").first()).toBeVisible();
});

test("6. complete a habit", async () => {
  await page.goto("/habits");
  const toggle = page.getByRole("button", { name: /^Stretch/ }).first();
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(/1 day/).first()).toBeVisible();
});

test("7. add a book and log a reading session", async () => {
  await page.goto("/growth/reading");
  await page.getByRole("button", { name: "Add book" }).click();
  await page.getByLabel("Title").fill("The Overstory");
  await page.getByLabel("Total pages").fill("500");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "The Overstory" })).toBeVisible();
  await page.getByRole("button", { name: "Log time" }).click();
  await page.getByRole("spinbutton", { name: "Minutes", exact: true }).fill("25");
  await page.getByLabel("To page").fill("40");
  await page.getByRole("button", { name: "Save session" }).click();
  await expect(page.getByText("Page 40 of 500")).toBeVisible();
  await expect(page.getByText("25 min").first()).toBeVisible();
});

test("8. add a workout", async () => {
  await page.goto("/growth/fitness");
  await page.getByRole("button", { name: "Log a workout" }).click();
  await page.getByLabel("Type").fill("Run");
  await page.getByRole("spinbutton", { name: "Minutes", exact: true }).fill("30");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/Run/).first()).toBeVisible();
  await expect(page.getByText("1 session")).toBeVisible();
});

test("9. review the daily dashboard", async () => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(user.name);
  await expect(page.getByText(/1\/1 habits/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reading" })).toBeVisible();
  await expect(page.getByText(/25 min read today/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Today's agenda" }).getByText("Book club")).toBeVisible();
  await expect(page.getByText(/next up is Book club at 19:00/)).toBeVisible();
});

test("10. change notification preferences", async () => {
  await page.goto("/settings/notifications");
  const quiet = page.getByRole("switch", { name: "Use quiet hours" });
  const before = await quiet.getAttribute("aria-checked");
  const saved = page.waitForResponse((r) => r.url().includes("/api/v1/preferences/") && r.request().method() === "PATCH");
  await quiet.click();
  expect((await saved).status()).toBe(200);
  await page.reload();
  await expect(page.getByRole("switch", { name: "Use quiet hours" })).toHaveAttribute("aria-checked", before === "true" ? "false" : "true");
  const tasksSwitch = page.getByRole("switch", { name: "Tasks" });
  const savedCat = page.waitForResponse((r) => r.url().includes("/api/v1/notification-preferences/") && r.request().method() === "PATCH");
  await tasksSwitch.click();
  expect((await savedCat).status()).toBe(200);
});

test("11. another user cannot access this user's data", async ({ browser }) => {
  const other = await browser.newPage();
  await other.goto("/register");
  await other.getByLabel("Email").fill(`intruder-${stamp}@daywell.test`);
  await other.getByLabel("Password").fill("Another-long-password-1");
  await other.getByRole("button", { name: "Create account" }).click();
  await expect(other).toHaveURL(/\/welcome$/);
  const status = await other.evaluate(async (id) => (await fetch(`/api/v1/tasks/${id}/`)).status, taskId);
  expect(status).toBe(404);
  const list = await other.evaluate(async () => (await fetch("/api/v1/tasks/")).json());
  expect(list.count).toBe(0);
  const journal = await other.evaluate(async () => (await fetch("/api/v1/reading/books/")).json());
  expect(journal.count).toBe(0);
  await other.close();
});
