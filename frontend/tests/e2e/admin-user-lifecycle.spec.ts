import { test, expect } from "@playwright/test";

/**
 * Full admin user lifecycle through the real UI against a live backend:
 * admin creates a user, the new user logs in, admin disables them, the
 * disabled user is blocked from logging in again, admin re-enables and
 * the user can log in once more. Requires a live backend (a real
 * Postgres behind DATABASE_URL) — unlike rbac-navigation.spec.ts, this
 * does not mock API calls, since the point is verifying the real
 * request/response cycle end to end.
 */
test.describe("Admin user lifecycle (live backend)", () => {
  test("create, login, disable, blocked, re-enable, login again", async ({ page }) => {
    const username = `e2e-user-${Date.now()}`;
    const password = "e2e-test-password-123";

    await page.goto("/login");
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password").fill("change-me");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });

    await page.goto("/admin/users");
    await page.getByPlaceholder("Username").fill(username);
    await page.getByPlaceholder("Password").fill(password);
    await page.getByRole("button", { name: /^create$/i }).click();
    await expect(page.getByText(username)).toBeVisible({ timeout: 10_000 });

    // New user logs in successfully
    await page.evaluate(() => window.localStorage.removeItem("sovereignai_token"));
    await page.goto("/login");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
    await expect(page.getByText("User Management")).toHaveCount(0); // real RBAC via real backend

    // Admin disables the new user
    await page.evaluate(() => window.localStorage.removeItem("sovereignai_token"));
    await page.goto("/login");
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password").fill("change-me");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });

    await page.goto("/admin/users");
    const row = page.locator("tr", { hasText: username });
    await expect(row.getByText("active")).toBeVisible();
    await row.getByTitle("Disable user").click();
    await expect(row.getByText("disabled")).toBeVisible({ timeout: 10_000 });

    // Disabled user cannot log in
    await page.evaluate(() => window.localStorage.removeItem("sovereignai_token"));
    await page.goto("/login");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/account disabled/i)).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/); // never made it past login

    // Admin re-enables; user can log in again
    await page.evaluate(() => window.localStorage.removeItem("sovereignai_token"));
    await page.goto("/login");
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password").fill("change-me");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });

    await page.goto("/admin/users");
    const row2 = page.locator("tr", { hasText: username });
    await row2.getByTitle("Re-enable user").click();
    await expect(row2.getByText("active")).toBeVisible({ timeout: 10_000 });

    await page.evaluate(() => window.localStorage.removeItem("sovereignai_token"));
    await page.goto("/login");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
  });
});
