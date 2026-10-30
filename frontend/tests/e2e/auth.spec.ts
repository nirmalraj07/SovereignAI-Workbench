import { test, expect } from "@playwright/test";

test.describe("Authentication flow", () => {
  test("unauthenticated user is redirected to /login", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });

  test("login page renders username/password fields", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByLabel("Username")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("submitting bad credentials shows an error, not a silent failure", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username").fill("nonexistent-user");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/invalid credentials|invalid/i)).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
  });

  test("fresh-install seed admin logs in directly without MFA (MFA starts disabled until enrolled)", async ({ page }) => {
    // The bootstrap admin seeded by alembic/versions/0003_user_mfa_and_seed.py
    // starts with MFA disabled — a fresh install needs a way in before
    // anyone has enrolled an authenticator via Settings. This intentionally
    // does NOT redirect to /mfa; that page is exercised directly below and
    // via the full enrollment flow in backend/tests/test_integration_api.py
    // TestMFAEnrollmentFlow (which also verifies login DOES require a code
    // once MFA is enabled).
    await page.goto("/login");
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password").fill("change-me");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
  });

  test("MFA verification page renders correctly when navigated to directly", async ({ page }) => {
    await page.goto("/mfa?username=admin&password=change-me");
    await expect(page.getByText(/two-factor verification/i)).toBeVisible();
    await expect(page.getByRole("textbox")).toBeVisible();
  });

  test("MFA page rejects a malformed code client-side (non-numeric input stripped)", async ({ page }) => {
    await page.goto("/mfa?username=admin&password=change-me");
    const input = page.getByRole("textbox");
    await input.fill("abc123xyz");
    await expect(input).toHaveValue("123");
  });
});
