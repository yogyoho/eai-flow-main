"use client";

import {
  Globe,
  Loader2,
  MonitorSmartphoneIcon,
  MoonIcon,
  Save,
  SunIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useState, useEffect } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  GroupedModelSelect,
  type ChatModelGroup,
} from "@/components/workspace/settings/grouped-model-select";
import { SettingsSection } from "@/components/workspace/settings/settings-section";
import { fetch } from "@/core/api/fetcher";
import { enUS, isLocale, zhCN, type Locale } from "@/core/i18n";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

interface SystemConfig {
  default_model?: string;
  fast_model?: string;
  embed_model?: string;
  enable_content_guard?: boolean;
  enable_content_guard_llm?: boolean;
  content_guard_llm_model?: string;
  theme?: string;
  ocr_services?: string;
}

interface OcrServiceEntry {
  name: string;
  base_url: string;
  api_key: string;
  model: string;
}

interface ModelChoice {
  name: string;
  status?: "available" | "unavailable" | "error";
  message?: string;
}

interface ModelStatus {
  status?: "available" | "unavailable" | "error";
  message?: string | null;
}

interface ModelValidationResponse {
  results: ModelValidationResult[];
}

interface ModelValidationResult {
  name: string;
  status: "available" | "unavailable" | "error";
  details: {
    exists: boolean;
    api_reachable: boolean | null;
    supports_thinking: boolean;
    supports_vision: boolean;
    has_credentials: boolean;
    message: string | null;
    latency_ms: number | null;
  };
}

export function BasicSettings() {
  const { t, locale, changeLocale } = useI18n();
  const [config, setConfig] = useState<SystemConfig>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [embedModelChoices, setEmbedModelChoices] = useState<ModelChoice[]>([]);
  const [chatModelGroups, setChatModelGroups] = useState<ChatModelGroup[]>([]);
  // EAI-CUSTOM (cpa v3 M3): OCR 服务注册表(掩码回显,写走专用 admin 端点)
  const [ocrServices, setOcrServices] = useState<OcrServiceEntry[]>([]);
  const [ocrDirty, setOcrDirty] = useState(false);
  const [ocrSaving, setOcrSaving] = useState(false);
  const [ocrStatus, setOcrStatus] = useState<
    Record<string, { ok: boolean; message: string } | "validating">
  >({});
  const [modelStatuses, setModelStatuses] = useState<
    Record<string, ModelStatus>
  >({});
  const [validatingModels, setValidatingModels] = useState<Set<string>>(
    new Set(),
  );
  const { theme, setTheme, systemTheme } = useTheme();
  const currentTheme = (theme ?? "system") as "system" | "light" | "dark";
  // 当前访问主机名 — 服务链接(RAGFlow/MinIO 等)用同一主机 + 各自端口,
  // 避免硬编码 localhost 导致生产环境跳转到 127.0.0.1。
  const [hostname, setHostname] = useState("localhost");

  const languageOptions: { value: Locale; label: string }[] = [
    { value: "en-US", label: enUS.locale.localName },
    { value: "zh-CN", label: zhCN.locale.localName },
  ];

  const themeOptions = [
    {
      id: "system",
      label: t.settings.basic.theme.system,
      description: t.settings.appearance.systemDescription,
      icon: MonitorSmartphoneIcon,
    },
    {
      id: "light",
      label: t.settings.basic.theme.light,
      description: t.settings.appearance.lightDescription,
      icon: SunIcon,
    },
    {
      id: "dark",
      label: t.settings.basic.theme.dark,
      description: t.settings.appearance.darkDescription,
      icon: MoonIcon,
    },
  ];

  useEffect(() => {
    void loadConfig();
    void loadModelChoices();
    void loadOcrServices();
    setHostname(window.location.hostname);
  }, []);

  const loadConfig = async () => {
    try {
      const response = await fetch("/api/extensions/config", {
        credentials: "include",
      });
      if (response.ok) {
        const data = await response.json();
        setConfig(data);
      }
    } catch (error) {
      console.error("Failed to load config:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadModelChoices = async () => {
    try {
      const response = await fetch("/api/extensions/models/choices", {
        credentials: "include",
      });
      if (response.ok) {
        const data = await response.json();
        setEmbedModelChoices(data.embed_models ?? []);
        setChatModelGroups(data.chat_models ?? []);
      }
    } catch (error) {
      console.error("Failed to load model choices:", error);
    }
  };

  const loadOcrServices = async () => {
    try {
      const response = await fetch("/api/extensions/ocr/services", {
        credentials: "include",
      });
      if (response.ok) {
        const data = await response.json();
        setOcrServices(data.services ?? []);
        setOcrDirty(false);
      }
    } catch (error) {
      console.error("Failed to load OCR services:", error);
    }
  };

  const setOcrService = (idx: number, patch: Partial<OcrServiceEntry>) => {
    setOcrServices((list) =>
      list.map((s, i) => (i === idx ? { ...s, ...patch } : s)),
    );
    setOcrDirty(true);
  };

  const saveOcrServices = async () => {
    setOcrSaving(true);
    try {
      const response = await fetch("/api/extensions/ocr/services", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ services: ocrServices }),
        credentials: "include",
      });
      const data = await response.json().catch(() => null);
      if (response.ok) {
        setOcrServices(data?.services ?? ocrServices);
        setOcrDirty(false);
        toast.success("OCR 服务已保存");
      } else {
        toast.error(data?.detail ?? "OCR 服务保存失败");
      }
    } catch {
      toast.error("OCR 服务保存失败");
    } finally {
      setOcrSaving(false);
    }
  };

  const validateOcrService = async (entry: OcrServiceEntry) => {
    setOcrStatus((s) => ({ ...s, [entry.name]: "validating" }));
    try {
      const response = await fetch("/api/extensions/ocr/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(entry),
        credentials: "include",
      });
      const data = await response.json().catch(() => null);
      if (response.ok && data) {
        setOcrStatus((s) => ({
          ...s,
          [entry.name]: { ok: !!data.ok, message: data.message ?? "" },
        }));
      } else {
        setOcrStatus((s) => ({
          ...s,
          [entry.name]: { ok: false, message: data?.detail ?? "校验请求失败" },
        }));
      }
    } catch {
      setOcrStatus((s) => ({
        ...s,
        [entry.name]: { ok: false, message: "校验请求失败：网络错误" },
      }));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch("/api/extensions/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
        credentials: "include",
      });
      if (response.ok) {
        toast.success(t.settings.basic.saveSuccess);
      } else {
        toast.error(t.settings.basic.saveFailed);
      }
    } catch {
      toast.error(t.settings.basic.saveFailed);
    } finally {
      setSaving(false);
    }
  };

  const handleValidateModel = async (modelName: string) => {
    if (validatingModels.has(modelName)) return;

    setValidatingModels((prev) => new Set([...prev, modelName]));
    try {
      const response = await fetch("/api/extensions/models/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ models: [modelName] }),
        credentials: "include",
      });
      if (response.ok) {
        const data = (await response.json()) as ModelValidationResponse;
        const result = data.results[0];
        if (result) {
          setModelStatuses((prev) => ({
            ...prev,
            [modelName]: {
              status: result.status,
              message: result.details.message,
            },
          }));
        }
      }
    } catch (error) {
      console.error("Failed to validate model:", error);
      setModelStatuses((prev) => ({
        ...prev,
        [modelName]: {
          status: "error",
          message: "Validation failed: network error",
        },
      }));
    } finally {
      setValidatingModels((prev) => {
        const next = new Set(prev);
        next.delete(modelName);
        return next;
      });
    }
  };

  const handleChange = (key: keyof SystemConfig, value: unknown) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 检索配置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t.settings.basic.retrieval.title}</CardTitle>
          <CardDescription>
            {t.settings.basic.retrieval.description}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="w-full space-y-2">
              <Label htmlFor="default_model">
                {t.settings.basic.retrieval.defaultModel}
              </Label>
              <GroupedModelSelect
                value={config.default_model ?? ""}
                onChange={(value) => handleChange("default_model", value)}
                groups={chatModelGroups}
                placeholder="例如: gpt-4o"
                modelStatuses={modelStatuses}
                validatingModels={validatingModels}
                onValidate={handleValidateModel}
              />
            </div>
            <div className="w-full space-y-2">
              <Label htmlFor="fast_model">
                {t.settings.basic.retrieval.fastModel}
              </Label>
              <GroupedModelSelect
                value={config.fast_model ?? ""}
                onChange={(value) => handleChange("fast_model", value)}
                groups={chatModelGroups}
                placeholder="用于快速响应的模型"
                modelStatuses={modelStatuses}
                validatingModels={validatingModels}
                onValidate={handleValidateModel}
              />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="w-full space-y-2">
              <Label htmlFor="embed_model">
                {t.settings.basic.retrieval.embedModel}
              </Label>
              <Select
                value={config.embed_model ?? ""}
                onValueChange={(value) => handleChange("embed_model", value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue
                    placeholder={t.settings.basic.retrieval.placeholder}
                  />
                </SelectTrigger>
                <SelectContent>
                  {embedModelChoices.map((model) => {
                    const embStatus = modelStatuses[model.name];
                    const statusColor =
                      embStatus?.status === "available"
                        ? "text-success"
                        : embStatus?.status === "unavailable"
                          ? "text-destructive"
                          : embStatus?.status === "error"
                            ? "text-amber-600 dark:text-amber-400"
                            : "text-muted-foreground";
                    const statusIcon =
                      embStatus?.status === "available"
                        ? "✓"
                        : embStatus?.status === "unavailable"
                          ? "✗"
                          : embStatus?.status === "error"
                            ? "⚠"
                            : "○";
                    return (
                      <SelectItem key={model.name} value={model.name}>
                        <div className="flex items-center gap-2">
                          <span>{model.name}</span>
                          <span className={statusColor}>{statusIcon}</span>
                        </div>
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* OCR 服务注册表（cpa v3 M3） */}
      <Card>
        <CardHeader>
          <CardTitle>OCR 服务</CardTitle>
          <CardDescription>
            注册OCR 服务（OpenAI 兼容 vision 协议，如 PaddleOCR-VL/ Qwen-VL）。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {ocrServices.length === 0 && (
            <p className="text-muted-foreground text-sm">
              尚未注册 OCR 服务。未注册时合同解析使用内建 eai-flow-ocr 引擎。
            </p>
          )}
          {ocrServices.map((s, i) => {
            const st = ocrStatus[s.name];
            return (
              <div key={`ocr-${i}`} className="space-y-2 rounded-lg border p-3">
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  <div className="space-y-1">
                    <Label>服务名称</Label>
                    <Input
                      value={s.name}
                      placeholder="例如：paddleocr-vl"
                      onChange={(e) =>
                        setOcrService(i, { name: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>Base URL</Label>
                    <Input
                      value={s.base_url}
                      placeholder="例如：http://192.168.2.38:8111/v1"
                      onChange={(e) =>
                        setOcrService(i, { base_url: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>API Key（留空 = 无鉴权）</Label>
                    <Input
                      value={s.api_key}
                      placeholder="******** 表示保持已存值"
                      onChange={(e) =>
                        setOcrService(i, { api_key: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>模型名</Label>
                    <Input
                      value={s.model}
                      placeholder="例如：paddleocr-vl-1.6"
                      onChange={(e) =>
                        setOcrService(i, { model: e.target.value })
                      }
                    />
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground text-xs">
                    {st === "validating"
                      ? "校验中…"
                      : st
                        ? st.ok
                          ? `✓ ${st.message}`
                          : `✗ ${st.message}`
                        : undefined}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={st === "validating"}
                      onClick={() => void validateOcrService(s)}
                    >
                      测试连接
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                      onClick={() => {
                        setOcrServices((list) =>
                          list.filter((_, j) => j !== i),
                        );
                        setOcrDirty(true);
                      }}
                    >
                      删除
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setOcrServices((list) => [
                  ...list,
                  { name: "", base_url: "", api_key: "", model: "" },
                ])
              }
            >
              + 添加服务
            </Button>
            <Button
              size="sm"
              onClick={saveOcrServices}
              disabled={ocrSaving || !ocrDirty}
            >
              {ocrSaving ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : null}
              保存 OCR 服务
            </Button>
            {ocrDirty && (
              <span className="text-sm text-amber-600 dark:text-amber-400">
                有未保存修改
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 内容审查配置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t.settings.basic.contentGuard.title}</CardTitle>
          <CardDescription>
            {t.settings.basic.contentGuard.description}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="enable_content_guard">
                {t.settings.basic.contentGuard.enable}
              </Label>
              <p className="text-muted-foreground text-sm">
                {t.settings.basic.contentGuard.enableHint}
              </p>
            </div>
            <Switch
              id="enable_content_guard"
              checked={config.enable_content_guard ?? false}
              onCheckedChange={(checked) =>
                handleChange("enable_content_guard", checked)
              }
            />
          </div>
          {config.enable_content_guard && (
            <>
              <Separator />
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="enable_content_guard_llm">
                    {t.settings.basic.contentGuard.enableLLM}
                  </Label>
                  <p className="text-muted-foreground text-sm">
                    {t.settings.basic.contentGuard.enableLLMHint}
                  </p>
                </div>
                <Switch
                  id="enable_content_guard_llm"
                  checked={config.enable_content_guard_llm ?? false}
                  onCheckedChange={(checked) =>
                    handleChange("enable_content_guard_llm", checked)
                  }
                />
              </div>
              {config.enable_content_guard_llm && (
                <div className="space-y-2">
                  <Label htmlFor="content_guard_llm_model">
                    {t.settings.basic.contentGuard.model}
                  </Label>
                  <GroupedModelSelect
                    value={config.content_guard_llm_model ?? ""}
                    onChange={(value) =>
                      handleChange("content_guard_llm_model", value)
                    }
                    groups={chatModelGroups}
                    placeholder={t.settings.basic.contentGuard.modelPlaceholder}
                    modelStatuses={modelStatuses}
                    validatingModels={validatingModels}
                    onValidate={handleValidateModel}
                  />
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* 主题与外观设置 */}
      <Card>
        <CardContent className="space-y-6">
          <SettingsSection
            title={t.settings.appearance.themeTitle}
            description={t.settings.appearance.themeDescription}
          >
            <div className="grid gap-3 lg:grid-cols-3">
              {themeOptions.map((option) => (
                <ThemePreviewCard
                  key={option.id}
                  icon={option.icon}
                  label={option.label}
                  description={option.description}
                  active={currentTheme === option.id}
                  mode={option.id as "system" | "light" | "dark"}
                  systemTheme={systemTheme}
                  onSelect={(value) => setTheme(value)}
                />
              ))}
            </div>
          </SettingsSection>

          <Separator />

          <SettingsSection
            title={t.settings.basic.language.title}
            description={t.settings.basic.language.description}
          >
            <Select
              value={locale}
              onValueChange={(value) => {
                if (isLocale(value)) {
                  changeLocale(value);
                }
              }}
            >
              <SelectTrigger className="w-[220px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {languageOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingsSection>
        </CardContent>
      </Card>

      {/* 服务链接 */}
      <Card>
        <CardHeader>
          <CardTitle>{t.settings.basic.services.title}</CardTitle>
          <CardDescription>
            {t.settings.basic.services.description}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            {/* EAI-CUSTOM: 遗留服务链接（neo4j/milvus/apiDocs 等部署中不存在）用环境开关隐藏，
                生产离线包设 NEXT_PUBLIC_SHOW_LEGACY_SERVICE_LINKS=false；dev 缺省 true 保持原样 */}
            {(process.env.NEXT_PUBLIC_SHOW_LEGACY_SERVICE_LINKS ?? "true") ===
              "true" && (
              <>
                <ServiceLinkCard
                  title={t.settings.basic.services.docCenter}
                  description={t.settings.basic.services.docCenterDesc}
                  href="#"
                />
                <ServiceLinkCard
                  title={t.settings.basic.services.neo4j}
                  description={t.settings.basic.services.neo4jDesc}
                  href={`http://${hostname}:7575/`}
                />
                <ServiceLinkCard
                  title={t.settings.basic.services.apiDocs}
                  description={t.settings.basic.services.apiDocsDesc}
                  href={`http://${hostname}:5050/docs`}
                />
                <ServiceLinkCard
                  title={t.settings.basic.services.milvus}
                  description={t.settings.basic.services.milvusDesc}
                  href={`http://${hostname}:9091/webui/`}
                />
              </>
            )}
            <ServiceLinkCard
              title={t.settings.basic.services.minio}
              description={t.settings.basic.services.minioDesc}
              href={`http://${hostname}:${process.env.NEXT_PUBLIC_MINIO_CONSOLE_PORT ?? "9001"}`}
            />
            <ServiceLinkCard
              title={t.settings.basic.services.ragflow}
              description={t.settings.basic.services.ragflowDesc}
              href={`http://${hostname}:${process.env.NEXT_PUBLIC_RAGFLOW_WEB_PORT ?? "9381"}/`}
            />
          </div>
        </CardContent>
      </Card>

      {/* 保存按钮 */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-2 h-4 w-4" />
          )}
          {t.settings.basic.save}
        </Button>
      </div>
    </div>
  );
}

function ThemePreviewCard({
  icon: Icon,
  label,
  description,
  active,
  mode,
  systemTheme,
  onSelect,
}: {
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  label: string;
  description: string;
  active: boolean;
  mode: "system" | "light" | "dark";
  systemTheme?: string;
  onSelect: (mode: "system" | "light" | "dark") => void;
}) {
  const previewMode =
    mode === "system" ? (systemTheme === "dark" ? "dark" : "light") : mode;
  return (
    <button
      type="button"
      onClick={() => onSelect(mode)}
      className={cn(
        "group flex h-full flex-col gap-3 rounded-lg border p-4 text-left transition-all",
        active
          ? "border-primary ring-primary/30 shadow-sm ring-2"
          : "hover:border-border hover:shadow-sm",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="bg-muted rounded-md p-2">
          <Icon className="size-4" />
        </div>
        <div className="space-y-1">
          <div className="text-sm leading-none font-semibold">{label}</div>
          <p className="text-muted-foreground text-xs leading-snug">
            {description}
          </p>
        </div>
      </div>
      <div
        className={cn(
          "relative overflow-hidden rounded-md border text-xs transition-colors",
          previewMode === "dark"
            ? "border-neutral-800 bg-neutral-900 text-neutral-200"
            : "border-slate-200 bg-white text-slate-900",
        )}
      >
        <div className="border-border/50 flex items-center gap-2 border-b px-3 py-2">
          <div
            className={cn(
              "h-2 w-2 rounded-full",
              previewMode === "dark" ? "bg-emerald-400" : "bg-emerald-500",
            )}
          />
          <div className="h-2 w-10 rounded-full bg-current/20" />
          <div className="h-2 w-6 rounded-full bg-current/15" />
        </div>
        <div className="grid grid-cols-[1fr_240px] gap-3 px-3 py-3">
          <div className="space-y-2">
            <div className="h-3 w-3/4 rounded-full bg-current/15" />
            <div className="h-3 w-1/2 rounded-full bg-current/10" />
            <div className="h-[90px] rounded-md border border-current/10 bg-current/5" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-md bg-current/10" />
              <div className="space-y-2">
                <div className="h-2 w-14 rounded-full bg-current/15" />
                <div className="h-2 w-10 rounded-full bg-current/10" />
              </div>
            </div>
            <div className="flex flex-col gap-1 rounded-md border border-dashed border-current/15 p-2">
              <div className="h-2 w-3/5 rounded-full bg-current/15" />
              <div className="h-2 w-2/5 rounded-full bg-current/10" />
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}

function ServiceLinkCard({
  title,
  description,
  href,
}: {
  title: string;
  description: string;
  href: string;
}) {
  return (
    <div className="hover:bg-accent/50 flex items-center justify-between rounded-lg border p-4 transition-colors">
      <div className="space-y-1">
        <h4 className="text-sm font-medium">{title}</h4>
        <p className="text-muted-foreground text-xs">{description}</p>
      </div>
      <Button variant="outline" size="sm" asChild>
        <a href={href} target="_blank" rel="noopener noreferrer">
          <Globe className="mr-2 h-4 w-4" />
          访问
        </a>
      </Button>
    </div>
  );
}
