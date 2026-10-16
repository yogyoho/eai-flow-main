// EAI-CUSTOM skip (2026-10-16, 上游同步): 本页为 EAI 有意替换的双模式登录页
// (工号+密码 / 邮箱OTP / SSO 条件按钮, 中文文案, 无注册表单 —— fde74fffc/ca7505131)。
// 这组上游 dom 测试钉的是上游单表单页契约(enUS.login.* 标签/sign-up 流程/
// account_disabled 文案), 与 EAI 页面结构不匹配; 停用账号的拒绝文案由 extensions
// 门面流程给出。上游若回归单表单页时再启用。

import { afterEach, beforeEach, expect, test, rs } from "@rstest/core";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import LoginPage from "@/app/(auth)/login/page";
import type * as AuthProviderModule from "@/core/auth/AuthProvider";
import { AuthDisabledContext, useAuth } from "@/core/auth/AuthProvider";
import type * as Setup from "@/core/auth/setup";
import { enUS } from "@/core/i18n/locales/en-US";

// Keep the real module (AuthDisabledContext must be the same object the
// page consumes); override only the hook.
rs.mock("@/core/auth/AuthProvider", () => ({
  ...(rs.requireActual<typeof AuthProviderModule>(
    "@/core/auth/AuthProvider",
  ) as object),
  useAuth: rs.fn(),
}));
rs.mock("@/core/i18n/hooks", () => ({ useI18n: () => ({ t: enUS }) }));
rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
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

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

beforeEach(() => {
  rs.mocked(useAuth).mockReturnValue({
    isAuthenticated: false,
  } as ReturnType<typeof useAuth>);
  globalThis.fetch = rs.fn(async () =>
    jsonResponse({ providers: [] }),
  ) as unknown as typeof globalThis.fetch;
});
afterEach(() => {
  cleanup();
  rs.clearAllMocks();
});

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText(enUS.login.email), {
    target: { value: "suspended@example.com" },
  });
  fireEvent.change(
    screen.getByLabelText<HTMLInputElement>(enUS.login.password),
    {
      target: { value: "correct-horse-battery" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: enUS.login.signIn }));
}

test.skip("an account_disabled rejection shows the localized reason", async () => {
  globalThis.fetch = rs.fn(async () =>
    jsonResponse(
      { detail: { code: "account_disabled", message: "Account disabled" } },
      401,
    ),
  ) as unknown as typeof globalThis.fetch;
  render(<LoginPage />);

  await waitFor(() => screen.getByRole("button", { name: enUS.login.signIn }));
  fillAndSubmit();

  expect(
    await screen.findByText(enUS.login.errors.account_disabled),
  ).toBeTruthy();
});

test.skip("other rejections keep showing the backend message", async () => {
  globalThis.fetch = rs.fn(async () =>
    jsonResponse(
      {
        detail: {
          code: "invalid_credentials",
          message: "Incorrect email or password",
        },
      },
      401,
    ),
  ) as unknown as typeof globalThis.fetch;
  render(<LoginPage />);

  await waitFor(() => screen.getByRole("button", { name: enUS.login.signIn }));
  fillAndSubmit();

  expect(await screen.findByText("Incorrect email or password")).toBeTruthy();
});

test.skip("a direct /login visit with a suspended session states the reason", () => {
  render(
    <AuthDisabledContext.Provider value={true}>
      <LoginPage />
    </AuthDisabledContext.Provider>,
  );

  // SSR verdict, not a login attempt: the message is present on mount.
  expect(screen.getByText(enUS.login.errors.account_disabled)).toBeTruthy();
});

test.skip("an ordinary /login visit shows no suspension note", () => {
  render(<LoginPage />);

  expect(screen.queryByText(enUS.login.errors.account_disabled)).toBeNull();
});

test.skip("sign-up keeps the backend message so a disabled account cannot be probed", async () => {
  globalThis.fetch = rs.fn(async () =>
    jsonResponse(
      { detail: { code: "account_disabled", message: "Account disabled" } },
      401,
    ),
  ) as unknown as typeof globalThis.fetch;
  render(<LoginPage />);

  await waitFor(() => screen.getByRole("button", { name: enUS.login.signIn }));
  // Switch to the register form, then submit against the same 401 code.
  fireEvent.click(
    screen.getByRole("button", { name: enUS.login.noAccountSignUp }),
  );
  fireEvent.change(screen.getByLabelText(enUS.login.email), {
    target: { value: "suspended@example.com" },
  });
  fireEvent.change(
    screen.getByLabelText<HTMLInputElement>(enUS.login.password),
    {
      target: { value: "correct-horse-battery" },
    },
  );
  fireEvent.click(
    screen.getByRole("button", { name: enUS.login.createAccount }),
  );

  expect(await screen.findByText("Account disabled")).toBeTruthy();
  expect(screen.queryByText(enUS.login.errors.account_disabled)).toBeNull();
});
