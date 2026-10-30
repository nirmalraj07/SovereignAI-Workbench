import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/lib/store";

function makeToken(payload: object): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = btoa(JSON.stringify(payload));
  return `${header}.${body}.fakesignature`;
}

describe("useAuthStore", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useAuthStore.setState({ token: null, user: null });
  });

  it("starts with no session", () => {
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("decodes username and role from a valid JWT on setSession", () => {
    const token = makeToken({ sub: "alice", role: "engineer", exp: 9999999999 });
    useAuthStore.getState().setSession(token);
    expect(useAuthStore.getState().user).toEqual({ username: "alice", role: "engineer" });
    expect(window.localStorage.getItem("sovereignai_token")).toBe(token);
  });

  it("clears session on logout", () => {
    useAuthStore.getState().setSession(makeToken({ sub: "bob", role: "admin" }));
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().token).toBeNull();
    expect(window.localStorage.getItem("sovereignai_token")).toBeNull();
  });

  it("hasRole respects the role hierarchy", () => {
    useAuthStore.getState().setSession(makeToken({ sub: "carol", role: "engineer" }));
    expect(useAuthStore.getState().hasRole("viewer")).toBe(true);
    expect(useAuthStore.getState().hasRole("engineer")).toBe(true);
    expect(useAuthStore.getState().hasRole("admin")).toBe(false);
  });

  it("hasRole is false with no session", () => {
    expect(useAuthStore.getState().hasRole("viewer")).toBe(false);
  });

  it("hydrate reads a token already in localStorage", () => {
    const token = makeToken({ sub: "dave", role: "auditor" });
    window.localStorage.setItem("sovereignai_token", token);
    useAuthStore.getState().hydrate();
    expect(useAuthStore.getState().user?.username).toBe("dave");
  });
});
