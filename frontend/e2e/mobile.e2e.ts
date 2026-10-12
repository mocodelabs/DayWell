import { expect, test } from "@playwright/test";

test("mobile: register, skip setup, and navigate with the bottom bar", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Email").fill(`mobile-${Date.now()}@daywell.test`);
  await page.getByLabel("Password").fill("Mobile-calm-mornings-1");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByRole("button", { name: "Skip setup" }).click();
  await expect(page).toHaveURL(/\/$/);
  const bottom = page.getByRole("navigation", { name: "Main" }).last();
  await bottom.getByRole("link", { name: "Tasks" }).click();
  await expect(page.getByRole("heading", { name: "Tasks" })).toBeVisible();
  await page.getByRole("button", { name: "Quick add" }).click();
  await page.getByLabel("What do you need to do?").fill("Water the plants today");
  await page.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByText("Water the plants")).toBeVisible();
  await bottom.getByRole("button", { name: "More" }).click();
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  // No horizontal scrolling on a phone.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
