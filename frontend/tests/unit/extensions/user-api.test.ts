import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { userApi } from "@/extensions/api";

describe("userApi.resetPassword", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("sends new_password in the JSON body, not the query string", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: "Password reset successfully" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await userApi.resetPassword("user-123", "NewPass123");

    const [url, init] = fetchMock.mock.calls[0]!;
    // Contract: backend expects a body { new_password }, never a URL query param
    expect(String(url)).toBe("/api/extensions/users/user-123/reset-password");
    expect(String(url)).not.toContain("new_password=");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ new_password: "NewPass123" });
  });
});
