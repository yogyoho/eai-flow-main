import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const replace = rs.fn();
const push = rs.fn();
// Next's app router object is stable across renders; a fresh object per call
// would re-run every effect that depends on it.
const router = { push, replace };
const redirect = rs.fn((url: string) => {
  throw new Error(`NEXT_REDIRECT ${url}`);
});
let searchParams = new URLSearchParams();

rs.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => window.location.pathname,
  useSearchParams: () => searchParams,
  redirect: (url: string) => redirect(url),
}));
rs.mock("@/env", () => ({
  env: { NEXT_PUBLIC_STATIC_WEBSITE_ONLY: "false" },
}));
rs.mock("@/core/auth/server", () => ({ getServerSideUser: rs.fn() }));
rs.mock("@/core/i18n/server", () => ({
  detectLocaleServer: async () => "en-US",
}));
rs.mock("@/core/i18n/context", () => ({
  I18nProvider: ({ children }: { children: ReactNode }) => children,
}));
rs.mock("@/core/i18n/hooks", () => ({ useI18n: () => ({ t: enUS }) }));
rs.mock("next-themes", () => ({
  useTheme: () => ({ theme: "light", resolvedTheme: "light" }),
}));
rs.mock("@/components/ui/flickering-grid", () => ({
  FlickeringGrid: () => null,
}));
rs.mock("@/core/auth/setup", () => ({
  ...(rs.requireActual<typeof Setup>("@/core/auth/setup") as object),
  fetchSetupStatus: rs.fn(async () => ({
    needs_setup: false,
    registration_enabled: true,
  })),
}));

import AuthCallbackPage from "@/app/(auth)/auth/callback/page";
import AuthLayout from "@/app/(auth)/layout";
import LoginPage from "@/app/(auth)/login/page";
import SetupPage from "@/app/(auth)/setup/page";
import { getServerSideUser } from "@/core/auth/server";
import type * as Setup from "@/core/auth/setup";
import type { AuthResult, User } from "@/core/auth/types";
import { enUS } from "@/core/i18n/locales/en-US";

const user: User = {
  id: "u-1",
  email: "sso@example.com",
  system_role: "user",
  needs_setup: false,
  oauth_provider: "keycloak",
};
const DEEP_LINK = "/workspace/chats/abc-123?tab=files";

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

async function renderAuthRoute(result: AuthResult, page: ReactNode) {
  rs.mocked(getServerSideUser).mockResolvedValue(result);
  render(await AuthLayout({ children: page }));
}

beforeEach(() => {
  // The auth pages fetch plain path strings.
  globalThis.fetch = rs.fn(async (input: string) =>
    input.endsWith("/api/v1/auth/me")
      ? jsonResponse(user)
      : jsonResponse({ providers: [] }),
  ) as unknown as typeof globalThis.fetch;
});
afterEach(() => {
  cleanup();
  rs.clearAllMocks();
  searchParams = new URLSearchParams();
});

describe("auth routes with a signed-in session", () => {
  it("sends the SSO callback to its next path", async () => {
    // The Gateway sets the session cookie on the same redirect that lands
    // here, so the layout always sees this request as authenticated.
    searchParams = new URLSearchParams({ next: DEEP_LINK });

    await renderAuthRoute({ tag: "authenticated", user }, <AuthCallbackPage />);

    expect(redirect).not.toHaveBeenCalled();
    await waitFor(() => expect(replace).toHaveBeenCalledWith(DEEP_LINK));
    expect(replace).toHaveBeenCalledTimes(1);
  });

  // `/\n//…` and `/\t//…` become `//evil.example/phish` once the URL parser
  // deletes the control character.
  const UNSAFE_NEXT = [
    "//evil.example/phish",
    "/\n//evil.example/phish",
    "/\t//evil.example/phish",
  ];

  it.each(UNSAFE_NEXT)(
    "sends the SSO callback to the workspace for unsafe next %j",
    async (next) => {
      searchParams = new URLSearchParams({ next });

      await renderAuthRoute(
        { tag: "authenticated", user },
        <AuthCallbackPage />,
      );

      await waitFor(() => expect(replace).toHaveBeenCalledWith("/workspace"));
      expect(replace).toHaveBeenCalledTimes(1);
    },
  );

  // EAI-CUSTOM skip (2026-11-08, 上游同步): LoginPage 在本 fork 是 EAI 有意替换的
  // 双模式登录页（工号+密码/邮箱验证码，见 login/page.tsx 头注释）——无
  // already-authenticated redirect（extensions 会话独立于核心 cookie 会话，
  // /login 须保持可达以供 extensions 重登）。上游三条 unsafe-next 断言
  // 不适用于 EAI 页面。AuthCallbackPage / SetupPage 仍为上游形态，测试保留。
  it.skip.each(UNSAFE_NEXT)(
    "sends a signed-in login visit to the workspace for unsafe next %j",
    async (next) => {
      searchParams = new URLSearchParams({ next });

      await renderAuthRoute({ tag: "authenticated", user }, <LoginPage />);

      await waitFor(() => expect(replace).toHaveBeenCalledWith("/workspace"));
      expect(replace).toHaveBeenCalledTimes(1);
    },
  );

  // EAI-CUSTOM skip (2026-11-08, 上游同步): 同上——EAI 双模式登录页不重定向
  // 已登录会话，且表单文案为中文（无 enUS.login.* 文案）。
  it.skip("sends a signed-in login visit to its next path without the form", async () => {
    searchParams = new URLSearchParams({ next: DEEP_LINK });

    await renderAuthRoute({ tag: "authenticated", user }, <LoginPage />);

    expect(redirect).not.toHaveBeenCalled();
    await waitFor(() => expect(replace).toHaveBeenCalledWith(DEEP_LINK));
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(enUS.login.email)).toBeNull();
    expect(screen.getByText(enUS.login.pleaseWait)).toBeTruthy();
  });

  it("sends a signed-in setup visit to the workspace", async () => {
    await renderAuthRoute({ tag: "authenticated", user }, <SetupPage />);

    expect(redirect).not.toHaveBeenCalled();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/workspace"));
  });
});

describe("auth routes without a session", () => {
  // EAI-CUSTOM skip (2026-11-08, 上游同步): 断言 enUS.login.email 标签，而 EAI
  // 双模式登录页为中文工号/验证码表单（有意替换，见 login/page.tsx 头注释）。
  it.skip("renders the sign-in form and stays on the page", async () => {
    searchParams = new URLSearchParams({ next: DEEP_LINK });

    await renderAuthRoute({ tag: "unauthenticated" }, <LoginPage />);

    expect(screen.getByLabelText(enUS.login.email)).toBeTruthy();
    expect(replace).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });
});
