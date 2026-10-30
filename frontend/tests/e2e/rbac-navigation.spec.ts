import { test, expect } from "@playwright/test";

/**
 * These tests seed localStorage with a hand-crafted (unsigned) JWT purely
 * to control the *client-side* role used for nav rendering — the backend
 * independently re-validates the signature on every API call (see
 * backend/tests/security/test_security.py), so this does not grant any
 * real access; it only lets us test the RBAC-aware sidebar in isolation
 * from a live backend.
 */
function fakeToken(role: string) {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64");
  const body = Buffer.from(JSON.stringify({ sub: "e2e-test-user", role, exp: 9999999999 })).toString("base64");
  return `${header}.${body}.fake`;
}

test.describe("RBAC-aware navigation", () => {
  test.beforeEach(async ({ page }) => {
    // These tests use an unsigned token to isolate the Sidebar's
    // client-side RBAC rendering — a real backend correctly rejects that
    // signature with 401 on every background poll (dashboard widgets,
    // notifications), which triggers the app's (intentional) global
    // logout-on-401 behavior and would wipe the nav before assertions
    // run. Stub every API call to 200 so this test stays isolated to
    // frontend logic regardless of whether a backend is reachable —
    // matching the comment above about not granting real access.
    await page.route("**/api/**", (route) => {
      const url = route.request().url();
      // Endpoints the frontend calls with array.filter()/array.map() need
      // an array stub, not {} — an object would throw at render time.
      const isArrayEndpoint = /\/api\/(notifications|admin\/models)(\?|$)/.test(url);
      route.fulfill({ status: 200, json: isArrayEndpoint ? [] : {} });
    });
  });

  test("viewer does not see admin-only nav items", async ({ page }) => {
    await page.addInitScript((token) => {
      window.localStorage.setItem("sovereignai_token", token);
    }, fakeToken("viewer"));
    await page.goto("/dashboard");
    await expect(page.getByText("User Management")).toHaveCount(0);
    await expect(page.getByText("Model Management")).toHaveCount(0);
    await expect(page.getByText("AI Chat")).toBeVisible();
  });

  test("admin sees all nav items including admin-only routes", async ({ page }) => {
    await page.addInitScript((token) => {
      window.localStorage.setItem("sovereignai_token", token);
    }, fakeToken("admin"));
    await page.goto("/dashboard");
    await expect(page.getByText("User Management")).toBeVisible();
    await expect(page.getByText("Model Management")).toBeVisible();
  });

  test("engineer sees coding and OCR workspaces but not admin routes", async ({ page }) => {
    await page.addInitScript((token) => {
      window.localStorage.setItem("sovereignai_token", token);
    }, fakeToken("engineer"));
    await page.goto("/dashboard");
    await expect(page.getByText("Coding Workspace")).toBeVisible();
    await expect(page.getByText("OCR Workspace")).toBeVisible();
    await expect(page.getByText("User Management")).toHaveCount(0);
  });
});
