"use client";

// EAI-CUSTOM: dual-mode login (工号+密码 / 邮箱+验证码) → EAI auth facade.
// Upstream deer-flow's email+password /api/v1/auth/login/local remains intact.

import { Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type LoginMode = "password" | "otp";

export default function LoginPage() {
  const [mode, setMode] = useState<LoginMode>("password");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [otpSent, setOtpSent] = useState(false);
  const [hasSsoProvider, setHasSsoProvider] = useState(false);

  useEffect(() => {
    const hasRedirect =
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("redirect");
    if (!hasRedirect) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  }, []);

  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  useEffect(() => {
    // EAI-CUSTOM: 仅当配置了 OIDC provider 时显示 SSO 按钮（避免未启用时的死按钮 404）
    fetch("/api/v1/auth/providers", { credentials: "include" })
      .then((r) => r.json().catch(() => ({ providers: [] })))
      .then((data) => setHasSsoProvider(Array.isArray(data?.providers) && data.providers.length > 0))
      .catch(() => setHasSsoProvider(false));
  }, []);

  const redirectAfterLogin = () => {
    const redirectUrl =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("redirect")
        : null;
    window.location.href = redirectUrl ?? "/";
  };

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const res = await fetch("/api/extensions/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(typeof data.detail === "string" ? data.detail : "登录失败");
        return;
      }
      redirectAfterLogin();
    } catch {
      setError("网络错误");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendCode = async () => {
    setError("");
    setOtpSent(false);
    try {
      const res = await fetch("/api/extensions/auth/otp/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(typeof data.detail === "string" ? data.detail : "发送失败");
        return;
      }
      setOtpSent(true);
      setCountdown(60);
    } catch {
      setError("网络错误");
    }
  };

  const handleOtpLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const res = await fetch("/api/extensions/auth/login/otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(typeof data.detail === "string" ? data.detail : "登录失败");
        return;
      }
      redirectAfterLogin();
    } catch {
      setError("网络错误");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex w-full bg-background">
      <div className="hidden lg:flex flex-col justify-between w-1/2 p-12 text-foreground relative overflow-hidden">
        <img
          src="/leftPanel.png?v=1"
          alt=""
          className="absolute inset-0 w-full h-full object-cover object-center"
          aria-hidden
        />
        <div className="absolute inset-0 bg-black/30" />
        <div className="relative z-10 mt-32">
          <h1 className="text-[56px] font-bold mb-8 tracking-wide text-white">
            吉林化工工程Agent
          </h1>
          <h2 className="text-3xl font-medium mb-6 text-white">
            企业智能体应用平台
          </h2>
          <p className="text-xl text-white/80">
            Harness驱动的多智能体协作、多模态交互、本地知识库
          </p>
        </div>
        <div className="relative z-10 text-sm text-white/60">
          &copy; 吉林化工工程有限公司 2026 v0.5
        </div>
      </div>

      <div className="flex-1 flex flex-col relative">
        <div className="absolute top-6 right-8">
          <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
            返回首页
          </Link>
        </div>

        <div className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-md bg-card rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-border p-10">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-foreground mb-2">欢迎回来</h2>
              <p className="text-muted-foreground text-sm">请输入您的账号信息登录</p>
            </div>

            <div className="grid grid-cols-2 gap-1 mb-6 p-1 bg-muted rounded-lg">
              {(["password", "otp"] as LoginMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setMode(m);
                    setError("");
                  }}
                  className={`py-2 text-sm rounded-md transition-colors ${
                    mode === m ? "bg-background shadow-sm font-medium" : "text-muted-foreground"
                  }`}
                >
                  {m === "password" ? "工号+密码" : "邮箱验证码"}
                </button>
              ))}
            </div>

            {/* EAI-CUSTOM: SSO 登录入口（通用 OIDC 第三门面，仅当配置了 provider 时显示） */}
            {hasSsoProvider && (
              <Link
                href="/api/extensions/auth/oidc/start?provider=keycloak"
                prefetch={false}
                className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border border-border py-2.5 text-sm text-muted-foreground hover:bg-muted transition-colors"
              >
                企业统一登录（SSO）
              </Link>
            )}

            {error && (
              <p className="text-destructive text-sm bg-destructive/10 rounded-lg px-3 py-2 mb-4">
                {error}
              </p>
            )}

            {mode === "password" ? (
              <form onSubmit={handlePasswordLogin} className="space-y-5">
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">工号</label>
                  <Input
                    type="text"
                    placeholder="请输入工号或邮箱"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="h-11"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">密码</label>
                  <div className="relative">
                    <Input
                      type={showPassword ? "text" : "password"}
                      placeholder="请输入密码"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="h-11 pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <Button type="submit" disabled={isLoading} className="w-full h-11 text-base">
                  {isLoading ? "登录中..." : "登录"}
                </Button>
              </form>
            ) : (
              <form onSubmit={handleOtpLogin} className="space-y-5">
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">邮箱</label>
                  <Input
                    type="email"
                    placeholder="name@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="h-11"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-foreground mb-1.5 block">验证码</label>
                  <div className="flex gap-2">
                    <Input
                      type="text"
                      inputMode="numeric"
                      maxLength={10}
                      placeholder="请输入验证码"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      required
                      className="h-11 flex-1"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      disabled={countdown > 0}
                      onClick={handleSendCode}
                      className="h-11 w-28 shrink-0"
                    >
                      {countdown > 0 ? `${countdown}s` : otpSent ? "重新发送" : "发送验证码"}
                    </Button>
                  </div>
                </div>
                <Button type="submit" disabled={isLoading} className="w-full h-11 text-base">
                  {isLoading ? "登录中..." : "登录"}
                </Button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
