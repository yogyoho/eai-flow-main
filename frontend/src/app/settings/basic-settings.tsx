"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/core/i18n/hooks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Globe, Loader2, Save } from "lucide-react";
import { toast } from "sonner";

interface SystemConfig {
  default_model?: string;
  fast_model?: string;
  embed_model?: string;
  reranker?: string;
  enable_content_guard?: boolean;
  enable_content_guard_llm?: boolean;
  content_guard_llm_model?: string;
  theme?: string;
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

interface ModelValidationRequest {
  models: string[];
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
  const { t } = useI18n();
  const [config, setConfig] = useState<SystemConfig>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [embedModelChoices, setEmbedModelChoices] = useState<ModelChoice[]>([]);
  const [rerankerChoices, setRerankerChoices] = useState<string[]>([]);
  const [modelStatuses, setModelStatuses] = useState<Record<string, ModelStatus>>({});
const [validatingModels, setValidatingModels] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadConfig();
    loadModelChoices();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await fetch("/api/extensions/config");
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
      const response = await fetch("/api/extensions/models/choices");
      if (response.ok) {
        const data = await response.json();
        setEmbedModelChoices(data.embed_models || []);
        setRerankerChoices(data.rerankers || []);
      }
    } catch (error) {
      console.error("Failed to load model choices:", error);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch("/api/extensions/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (response.ok) {
        toast.success(t.settings.basic.saveSuccess);
      } else {
        toast.error(t.settings.basic.saveFailed);
      }
    } catch (error) {
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

  const getModelStatusColor = (name: string) => {
    const status = modelStatuses[name];
    if (!status) return "text-gray-400";
    if (status.status === "available") return "text-green-500";
    if (status.status === "unavailable") return "text-red-500";
    if (status.status === "error") return "text-yellow-500";
    return "text-gray-400";
  };

  const getModelStatusIcon = (name: string) => {
    const status = modelStatuses[name];
    if (!status) return "○";
    if (status.status === "available") return "✓";
    if (status.status === "unavailable") return "✗";
    if (status.status === "error") return "⚠";
    return "○";
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  function ModelValidateButton({
    modelName,
  }: {
    modelName: string;
  }) {
    const isValidating = validatingModels.has(modelName);

    return (
      <button
        type="button"
        onClick={() => handleValidateModel(modelName)}
        disabled={isValidating}
        className="ml-2 p-1 hover:bg-accent rounded transition-colors"
        title={isValidating ? t.settings.basic.validating : t.settings.basic.validateModel}
      >
        {isValidating ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <span className="text-sm text-muted-foreground">{t.settings.basic.validateModel}</span>
        )}
      </button>
    );
  }

  return (
    <div className="space-y-6">
      {/* 检索配置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t.settings.basic.retrieval.title}</CardTitle>
          <CardDescription>{t.settings.basic.retrieval.description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label htmlFor="default_model">{t.settings.basic.retrieval.defaultModel}</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="default_model"
                  value={config.default_model || ""}
                  onChange={(e) => handleChange("default_model", e.target.value)}
                  placeholder="例如: gpt-4o"
                  className="flex-1"
                />
                {config.default_model && (
                  <>
                    <ModelValidateButton modelName={config.default_model} />
                    <span
                      className={getModelStatusColor(config.default_model)}
                      title={modelStatuses[config.default_model]?.message || ""}
                    >
                      {getModelStatusIcon(config.default_model)}
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="fast_model">{t.settings.basic.retrieval.fastModel}</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="fast_model"
                  value={config.fast_model || ""}
                  onChange={(e) => handleChange("fast_model", e.target.value)}
                  placeholder="用于快速响应的模型"
                  className="flex-1"
                />
                {config.fast_model && (
                  <>
                    <ModelValidateButton modelName={config.fast_model} />
                    <span
                      className={getModelStatusColor(config.fast_model)}
                      title={modelStatuses[config.fast_model]?.message || ""}
                    >
                      {getModelStatusIcon(config.fast_model)}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label htmlFor="embed_model">{t.settings.basic.retrieval.embedModel}</Label>
              <Select
                value={config.embed_model || ""}
                onValueChange={(value) => handleChange("embed_model", value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t.settings.basic.retrieval.placeholder} />
                </SelectTrigger>
                <SelectContent>
                  {embedModelChoices.map((model) => (
                    <SelectItem key={model.name} value={model.name}>
                      <div className="flex items-center gap-2">
                        <span>{model.name}</span>
                        <span className={getModelStatusColor(model.name)}>
                          {getModelStatusIcon(model.name)}
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="reranker">{t.settings.basic.retrieval.reranker}</Label>
              <Select
                value={config.reranker || ""}
                onValueChange={(value) => handleChange("reranker", value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t.settings.basic.retrieval.placeholder} />
                </SelectTrigger>
                <SelectContent>
                  {rerankerChoices.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 内容审查配置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t.settings.basic.contentGuard.title}</CardTitle>
          <CardDescription>{t.settings.basic.contentGuard.description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="enable_content_guard">{t.settings.basic.contentGuard.enable}</Label>
              <p className="text-sm text-muted-foreground">
                {t.settings.basic.contentGuard.enableHint}
              </p>
            </div>
            <Switch
              id="enable_content_guard"
              checked={config.enable_content_guard || false}
              onCheckedChange={(checked) => handleChange("enable_content_guard", checked)}
            />
          </div>
          {config.enable_content_guard && (
            <>
              <Separator />
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="enable_content_guard_llm">{t.settings.basic.contentGuard.enableLLM}</Label>
                  <p className="text-sm text-muted-foreground">
                    {t.settings.basic.contentGuard.enableLLMHint}
                  </p>
                </div>
                <Switch
                  id="enable_content_guard_llm"
                  checked={config.enable_content_guard_llm || false}
                  onCheckedChange={(checked) => handleChange("enable_content_guard_llm", checked)}
                />
              </div>
              {config.enable_content_guard_llm && (
                <div className="space-y-2">
                  <Label htmlFor="content_guard_llm_model">{t.settings.basic.contentGuard.model}</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="content_guard_llm_model"
                      value={config.content_guard_llm_model || ""}
                      onChange={(e) => handleChange("content_guard_llm_model", e.target.value)}
                      placeholder={t.settings.basic.contentGuard.modelPlaceholder}
                      className="flex-1"
                    />
                    {config.content_guard_llm_model && (
                      <>
                        <ModelValidateButton modelName={config.content_guard_llm_model} />
                        <span
                          className={getModelStatusColor(config.content_guard_llm_model)}
                          title={modelStatuses[config.content_guard_llm_model]?.message || ""}
                        >
                          {getModelStatusIcon(config.content_guard_llm_model)}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* 主题设置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t.settings.basic.theme.title}</CardTitle>
          <CardDescription>{t.settings.basic.theme.description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Select
            value={config.theme || "system"}
            onValueChange={(value) => handleChange("theme", value)}
          >
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder={t.settings.basic.theme.system} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="system">{t.settings.basic.theme.system}</SelectItem>
              <SelectItem value="light">{t.settings.basic.theme.light}</SelectItem>
              <SelectItem value="dark">{t.settings.basic.theme.dark}</SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {/* 服务链接 */}
      <Card>
        <CardHeader>
          <CardTitle>{t.settings.basic.services.title}</CardTitle>
          <CardDescription>{t.settings.basic.services.description}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <ServiceLinkCard
              title={t.settings.basic.services.docCenter}
              description={t.settings.basic.services.docCenterDesc}
              href="#"
            />
            <ServiceLinkCard
              title={t.settings.basic.services.neo4j}
              description={t.settings.basic.services.neo4jDesc}
              href="http://localhost:7575/"
            />
            <ServiceLinkCard
              title={t.settings.basic.services.apiDocs}
              description={t.settings.basic.services.apiDocsDesc}
              href="http://localhost:5050/docs"
            />
            <ServiceLinkCard
              title={t.settings.basic.services.minio}
              description={t.settings.basic.services.minioDesc}
              href="http://localhost:9001"
            />
            <ServiceLinkCard
              title={t.settings.basic.services.milvus}
              description={t.settings.basic.services.milvusDesc}
              href="http://localhost:9091/webui/"
            />
          </div>
        </CardContent>
      </Card>

      {/* 保存按钮 */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
          {t.settings.basic.save}
        </Button>
      </div>
    </div>
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
    <div className="flex items-center justify-between p-4 border rounded-lg hover:bg-accent/50 transition-colors">
      <div className="space-y-1">
        <h4 className="font-medium text-sm">{title}</h4>
        <p className="text-xs text-muted-foreground">{description}</p>
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
