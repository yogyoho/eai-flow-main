"use client";

import { User, Lock, Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/extensions/api";
import { useAuth } from "@/extensions/hooks/useAuth";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();

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
      await login({ username, password });
      const redirectUrl =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("redirect")
          : null;
      window.location.href = redirectUrl ?? "/workspace/chats/new";
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "登录失败";
      setError(message);
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
          <h1 className="text-[56px] font-bold mb-8 tracking-wide text-white">华宇工程Agent</h1>
          <h2 className="text-3xl font-medium mb-6 text-white">企业智能体应用平台</h2>
          <p className="text-xl text-white/80">Harness驱动的多智能体协作、多模态交互、本地知识库</p>
        </div>
        <div className="relative z-10 text-sm text-white/60">
          © 北京华宇工程有限公司 2026 v0.5
        </div>
      </div>

      {/* Right - Login Form */}
      <div className="flex-1 flex flex-col relative">
        <div className="absolute top-6 right-8">
          <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
            返回首页
          </Link>
        </div>

        <div className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-md bg-card rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.08)] border border-border p-10">
            <div className="mb-8">
              <p className="text-muted-foreground text-sm mb-2">欢迎登录</p>
              <h2 className="text-3xl font-bold text-primary mb-3">华宇工程Agent</h2>
              <p className="text-muted-foreground text-md">企业智能体应用平台</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-lg">{error}</div>
              )}
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  <span className="text-destructive mr-1">*</span>用户名
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <User className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <Input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="pl-9"
                    placeholder="请输入用户名"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  <span className="text-destructive mr-1">*</span>密码
                </label>
                <div className="relative flex items-center">
                  <div className="absolute left-3 z-10 pointer-events-none">
                    <Lock className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <Input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pl-9 pr-10"
                    placeholder="请输入密码"
                    required
                  />
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      setShowPassword((v) => !v);
                    }}
                    className="absolute right-3 text-muted-foreground hover:text-foreground focus:outline-none cursor-pointer select-none"
                    aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>

              <div className="pt-4">
                <Button
                  type="submit"
                  className="w-full"
                  disabled={isLoading}
                >
                  {isLoading ? "登录中..." : "登录"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
