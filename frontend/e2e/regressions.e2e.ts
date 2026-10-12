import { expect, test } from "@playwright/test";

/** Browser-level regression checks for previously fixed bugs. */
test("calendar week view opens scrolled to the user's working hours", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Email").fill(`scroll-${Date.now()}@daywell.test`);
  await page.getByLabel("Password").fill("Scroll-check-password-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByRole("button", { name: "Skip setup" }).click();
  await expect(page).toHaveURL(/\/$/);
  const status = await page.evaluate(async () => {
    const csrf = document.cookie.split("; ").find((c) => c.startsWith("daywell_csrftoken="))!.split("=")[1];
    const res = await fetch("/api/v1/preferences/", { method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf }, body: JSON.stringify({ work_start: "13:00" }) });
    return res.status;
  });
  expect(status).toBe(200);
  await page.goto("/calendar");
  const slot = page.locator('.fc-timegrid-slot-label[data-time="13:00:00"]');
  await expect(slot).toBeVisible();
  const offset = await page.evaluate(() => {
    const scroller = document.querySelector('[role="region"][aria-label^="Calendar"]') as HTMLElement;
    const row = document.querySelector('.fc-timegrid-slot-label[data-time="13:00:00"]') as HTMLElement;
    return row.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
  });
  // 13:00 sits at (or within a slot of) the top of the scroll area rather than far below midnight.
  expect(Math.abs(offset)).toBeLessThan(60);
});
