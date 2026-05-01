"use client";

import { Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const hasRedirect =
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("redirect");
    if (!hasRedirect) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const res = await fetch("/api/v1/auth/login/local", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
        credentials: "include",
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail =
          typeof data.detail === "object" && data.detail?.message
            ? data.detail.message
            : typeof data.detail === "string"
              ? data.detail
              : "Login failed";
        setError(detail);
        return;
      }

      const redirectUrl =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("redirect")
          : null;
      window.location.href = redirectUrl ?? "/workspace/chats/new";
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Network error"
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex w-full bg-background">
      {/* Left - Background & Text */}
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
            华宇工程Agent
          </h1>
          <h2 className="text-3xl font-medium mb-6 text-white">
            企业智能体应用平台
          </h2>
          <p className="text-xl text-white/80">
            Harness驱动的多智能体协作、多模态交互、本地知识库
          </p>
        </div>
        <div className="relative z-10 text-sm text-white/60">
          &copy; 北京华宇工程有限公司 2026 v0.5
        </div>
      </div>

      {/* Right - Login Form */}
      <div className="flex-1 flex flex-col relative">
        <div className="absolute top-6 right-8">
          <Link
            href="/"
            className="text-muted-foreground hover:text-foreground text-sm"
          >
            返回首页
          </Link>
        </div>

        <div className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-md bg-card rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-border p-10">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-foreground mb-2">
                欢迎回来
              </h2>
              <p className="text-muted-foreground text-sm">
                请输入您的账号信息登录
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="text-sm font-medium text-foreground mb-1.5 block">
                  邮箱
                </label>
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
                <label className="text-sm font-medium text-foreground mb-1.5 block">
                  密码
                </label>
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
                    {showPassword ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>

              {error && (
                <p className="text-destructive text-sm bg-destructive/10 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                disabled={isLoading}
                className="w-full h-11 text-base"
              >
                {isLoading ? "登录中..." : "登录"}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
