import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Automated accessibility checks (axe-core, WCAG 2.0/2.1/2.2 A + AA rule sets) on the critical screens and dialogs,
 * plus keyboard/focus, target-size, reflow, text-resize and reduced-motion checks that axe cannot fully cover.
 * Automated tooling finds a subset of WCAG issues — see docs/ACCESSIBILITY.md for the manual checks still required.
 */
test.describe.configure({ mode: "serial" });

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
let page: Page;

async function axe(p: Page, label: string) {
  const results = await new AxeBuilder({ page: p }).withTags(TAGS).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const summary = results.violations.map((v) => `${v.impact} ${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  if (summary.length) console.log(`[axe] ${label}\n  ${summary.join("\n  ")}`);
  expect(serious, `${label}: serious/critical axe violations`).toEqual([]);
  return results.violations;
}

async function csrfFetch(p: Page, method: string, url: string, body?: unknown) {
  return p.evaluate(async ([m, u, b]) => {
    const t = document.cookie.split("; ").find((c) => c.startsWith("daywell_csrftoken="))!.split("=")[1];
    const r = await fetch(u as string, { method: m as string, headers: { "Content-Type": "application/json", "X-CSRFToken": t }, body: b ? JSON.stringify(b) : undefined });
    return r.status;
  }, [method, url, body] as const);
}

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext()).newPage();
});

test("auth pages are accessible", async () => {
  await page.goto("/login");
  await axe(page, "login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveAttribute("aria-invalid", "true");
  await axe(page, "login with errors");
  await page.goto("/register");
  await axe(page, "register");
});

test("skip link is the first tab stop and moves focus to main content", async () => {
  await page.getByLabel("Email").fill(`a11y-${Date.now()}@daywell.test`);
  await page.getByLabel("Password").fill("Accessible-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await axe(page, "onboarding");
  await page.getByRole("button", { name: "Skip setup" }).click();
  await expect(page).toHaveURL(/\/$/);
  expect(await csrfFetch(page, "PATCH", "/api/v1/preferences/", { modules: { reading: true, fitness: true, hydration: true, journal: true, goals: true, sleep: true, mindfulness: true } })).toBe(200);
  expect(await csrfFetch(page, "POST", "/api/v1/tasks/", { title: "Accessible task", scheduled_date: new Date().toISOString().slice(0, 10) })).toBe(201);
  expect(await csrfFetch(page, "POST", "/api/v1/habits/", { name: "Stretch", schedule_rule: "FREQ=DAILY" })).toBe(201);
  await page.reload();
  await expect(page.locator("main h1").first()).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});

const PAGES = ["/", "/tasks", "/tasks?view=matrix", "/calendar", "/habits", "/growth/reading", "/growth/fitness", "/growth/affirmations",
  "/growth/hydration", "/growth/sleep", "/growth/journal", "/growth/mindfulness", "/insights", "/notifications", "/reminders",
  "/settings/profile", "/settings/rhythm", "/settings/notifications", "/settings/modules", "/settings/dashboard", "/settings/appearance", "/settings/privacy"];

for (const path of PAGES) {
  test(`page ${path} has no serious axe violations`, async () => {
    await page.goto(path);
    await expect(page.locator("main h1").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    await axe(page, path);
  });
}

test("dialogs trap focus, close with Escape and return focus", async () => {
  await page.goto("/tasks");
  const trigger = page.getByRole("button", { name: "New task" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New task" });
  await expect(dialog).toBeVisible();
  await expect(page.getByLabel("Title")).toBeFocused();
  await axe(page, "task form dialog");
  for (let i = 0; i < 40; i++) await page.keyboard.press("Tab");
  expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true); // focus never escapes
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  await page.goto("/");
  await page.getByRole("button", { name: "Quick add" }).first().click();
  await page.getByLabel("What do you need to do?").fill("Call mum tomorrow at 6 pm");
  await axe(page, "quick add with interpretation");
  await page.keyboard.press("Escape");
});

test("ringing alarm dialog is accessible and keyboard-operable", async () => {
  await page.goto("/settings/notifications");
  await page.getByRole("button", { name: "Test alarm now" }).click();
  const alarm = page.getByRole("alertdialog");
  await expect(alarm).toBeVisible({ timeout: 30_000 });
  await expect(alarm).toHaveAccessibleName("Test alarm");
  await expect(alarm.getByRole("button", { name: /^Snooze \d+ min$/ })).toBeFocused();
  await axe(page, "alarm dialog");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter"); // the next control is Dismiss
  await expect(alarm).toBeHidden();
});

test("calendar toolbar and grid are keyboard operable", async () => {
  await page.goto("/calendar");
  const heading = page.locator("main h2[aria-live]");
  await expect(heading).not.toHaveText("");
  const before = await heading.textContent();
  const next = page.getByRole("button", { name: "Next week" });
  await next.focus();
  await page.keyboard.press("Enter");
  await expect(heading).not.toHaveText(before ?? "");
  const region = page.getByRole("region", { name: /^Calendar/ });
  await region.focus();
  await expect(region).toBeFocused();
  const top = await region.evaluate((el) => el.scrollTop);
  expect(top).toBeGreaterThan(0); // opened scrolled to working hours
  await page.keyboard.press("PageUp"); // the focused region scrolls with the keyboard
  expect(await region.evaluate((el) => el.scrollTop)).toBeLessThan(top);
  await page.getByRole("radio", { name: "Month" }).click();
  await expect(page.locator(".fc-daygrid")).toBeVisible();
  await axe(page, "calendar month view");
});

test("touch targets are at least 24×24 CSS px (WCAG 2.5.8) on mobile", async ({ browser }) => {
  const mctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  await mctx.addCookies(await page.context().cookies());
  const mobile = await mctx.newPage();
  const tooSmall: string[] = [];
  for (const path of ["/", "/tasks", "/habits", "/settings/notifications"]) {
    await mobile.goto(path);
    await mobile.waitForLoadState("networkidle");
    tooSmall.push(...(await mobile.evaluate(() => {
      const out: string[] = [];
      document.querySelectorAll("main a, main button, main input, main select, nav a, nav button").forEach((el) => {
        // An input inside a <label> is activated by the whole label: that is the effective target (WCAG 2.5.8).
        const label = el instanceof HTMLInputElement ? el.closest("label") : null;
        const r = (label ?? (el as HTMLElement)).getBoundingClientRect();
        const inline = getComputedStyle(el).display === "inline" && el.closest("p");
        const hiddenInput = el instanceof HTMLInputElement && (el.type === "hidden" || r.width === 0);
        if (r.width === 0 || inline || hiddenInput) return;
        if (r.width < 24 || r.height < 24) out.push(`${location.pathname} ${el.tagName.toLowerCase()} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 30)}" ${Math.round(r.width)}×${Math.round(r.height)}`);
      });
      return out;
    })));
    await axe(mobile, `mobile ${path}`);
  }
  expect(tooSmall).toEqual([]);
  await mctx.close();
});

test("reflow at 320 CSS px and 200% text without horizontal scrolling", async ({ browser }) => {
  const nctx = await browser.newContext({ viewport: { width: 320, height: 640 } });
  await nctx.addCookies(await page.context().cookies());
  const narrow = await nctx.newPage();
  for (const path of ["/", "/tasks", "/settings/notifications"]) {
    await narrow.goto(path);
    await narrow.waitForLoadState("networkidle");
    expect(await narrow.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `reflow ${path}`).toBe(true);
  }
  await nctx.close();
  const bctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await bctx.addCookies(await page.context().cookies());
  const big = await bctx.newPage();
  await big.goto("/");
  await big.addStyleTag({ content: "html { font-size: 200% !important; }" });
  await big.waitForTimeout(200);
  expect(await big.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "200% text").toBe(true);
  await bctx.close();
});

test("reduced motion disables animation", async ({ browser }) => {
  const ctx = await browser.newContext({ reducedMotion: "reduce" });
  await ctx.addCookies(await page.context().cookies());
  const p = await ctx.newPage();
  await p.goto("/");
  await p.waitForLoadState("networkidle");
  const longest = await p.evaluate(() => Math.max(0, ...[...document.querySelectorAll("*")].map((el) => parseFloat(getComputedStyle(el).animationDuration) || 0)));
  expect(longest).toBeLessThan(0.01);
  await ctx.close();
});
