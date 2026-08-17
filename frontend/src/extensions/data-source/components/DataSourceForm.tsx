"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  ChevronDown,
  Database,
  Globe,
  Key,
  Loader2,
  Shield,
  Upload,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type {
  AuthType,
  CreateDataSourceRequest,
  DataSource,
  DataSourceType,
  SyncMode,
} from "../types";
import {
  AUTH_TYPE_LABELS,
  DATA_SOURCE_TYPE_LABELS,
  SYNC_MODE_LABELS,
} from "../types";

// ─── Custom Select ─────────────────────────────────────────────────────────────

interface SelectOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
}

function CustomSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-sm",
          "bg-background border transition-all duration-150",
          open
            ? "border-primary ring-ring/50 shadow-sm ring-2"
            : "border-input hover:border-input hover:shadow-sm",
        )}
      >
        <span
          className={cn(
            "flex min-w-0 items-center gap-2",
            selected ? "text-foreground" : "text-muted-foreground",
          )}
        >
          {selected?.icon && (
            <span className="text-muted-foreground shrink-0">
              {selected.icon}
            </span>
          )}
          <span className="truncate">{selected?.label ?? "请选择"}</span>
        </span>
        <ChevronDown
          className={cn(
            "text-muted-foreground h-4 w-4 shrink-0 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="border-border bg-background absolute top-full right-0 left-0 z-50 mt-1.5 overflow-hidden rounded-xl border shadow-lg shadow-black/5"
          >
            {options.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm transition-colors",
                  o.value === value
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-foreground hover:bg-muted",
                )}
              >
                {o.icon && (
                  <span
                    className={cn(
                      "shrink-0",
                      o.value === value
                        ? "text-primary"
                        : "text-muted-foreground",
                    )}
                  >
                    {o.icon}
                  </span>
                )}
                {o.label}
                {o.value === value && (
                  <CheckCircle2 className="text-primary ml-auto h-3.5 w-3.5 shrink-0" />
                )}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Connection config forms by type ──────────────────────────────────────────

function DatabaseConfigForm({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const update = (key: string, value: string) => {
    onChange({ ...config, [key]: value });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-foreground mb-1 block text-sm font-medium">
            主机地址
          </label>
          <Input
            type="text"
            value={(config.host as string) ?? ""}
            onChange={(e) => update("host", e.target.value)}
            placeholder="例如：localhost"
            className="w-full"
          />
        </div>
        <div>
          <label className="text-foreground mb-1 block text-sm font-medium">
            端口
          </label>
          <Input
            type="text"
            value={(config.port as string) ?? ""}
            onChange={(e) => update("port", e.target.value)}
            placeholder="例如：5432"
            className="w-full"
          />
        </div>
      </div>
      <div>
        <label className="text-foreground mb-1 block text-sm font-medium">
          数据库名称
        </label>
        <Input
          type="text"
          value={(config.database as string) ?? ""}
          onChange={(e) => update("database", e.target.value)}
          placeholder="例如：mydb"
          className="w-full"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-foreground mb-1 block text-sm font-medium">
            用户名
          </label>
          <Input
            type="text"
            value={(config.username as string) ?? ""}
            onChange={(e) => update("username", e.target.value)}
            placeholder="用户名"
            className="w-full"
          />
        </div>
        <div>
          <label className="text-foreground mb-1 block text-sm font-medium">
            密码
          </label>
          <Input
            type="password"
            value={(config.password as string) ?? ""}
            onChange={(e) => update("password", e.target.value)}
            placeholder="密码"
            className="w-full"
          />
        </div>
      </div>
    </div>
  );
}

function ApiConfigForm({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const update = (key: string, value: string) => {
    onChange({ ...config, [key]: value });
  };

  return (
    <div>
      <label className="text-foreground mb-1 block text-sm font-medium">
        API 地址
      </label>
      <Input
        type="text"
        value={(config.url as string) ?? ""}
        onChange={(e) => update("url", e.target.value)}
        placeholder="例如：https://api.example.com/v1"
        className="w-full"
      />
    </div>
  );
}

function FileConfigForm({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const update = (key: string, value: string) => {
    onChange({ ...config, [key]: value });
  };

  return (
    <div>
      <label className="text-foreground mb-1 block text-sm font-medium">
        文件路径
      </label>
      <Input
        type="text"
        value={(config.path as string) ?? ""}
        onChange={(e) => update("path", e.target.value)}
        placeholder="例如：/data/files/dataset.csv"
        className="w-full"
      />
    </div>
  );
}

function GisConfigForm({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileName = (config.file_name as string) ?? "";

  const addFile = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    if (file) {
      onChange({ ...config, file_name: file.name, file_size: file.size });
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    addFile(e.dataTransfer.files);
  };

  return (
    <div>
      <label className="text-foreground mb-1 block text-sm font-medium">
        GIS 数据文件
      </label>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          dragOver
            ? "border-primary bg-primary/10"
            : "border-input hover:border-primary/50 hover:bg-muted",
        )}
      >
        <Upload className="text-muted-foreground mx-auto mb-3 h-8 w-8" />
        <p className="text-foreground text-sm font-medium">
          {fileName || "拖拽文件到此处，或点击选择"}
        </p>
        <p className="text-muted-foreground mt-1 text-xs">
          支持 Shapefile、GeoJSON、KML 等格式
        </p>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept=".shp,.geojson,.json,.kml,.kmz,.gpx"
          onChange={(e) => addFile(e.target.files)}
        />
      </div>
    </div>
  );
}

// ─── DataSourceForm ────────────────────────────────────────────────────────────

const TYPE_OPTIONS: SelectOption[] = Object.entries(
  DATA_SOURCE_TYPE_LABELS,
).map(([value, label]) => ({
  value,
  label,
  icon: (() => {
    switch (value) {
      case "database":
        return <Database className="h-3.5 w-3.5" />;
      case "api":
        return <Key className="h-3.5 w-3.5" />;
      case "file":
        return <Upload className="h-3.5 w-3.5" />;
      case "gis":
        return <Globe className="h-3.5 w-3.5" />;
      default:
        return undefined;
    }
  })(),
}));

const AUTH_TYPE_OPTIONS: SelectOption[] = Object.entries(AUTH_TYPE_LABELS).map(
  ([value, label]) => ({
    value,
    label,
    icon: <Shield className="h-3.5 w-3.5" />,
  }),
);

const SYNC_MODE_OPTIONS: SelectOption[] = Object.entries(SYNC_MODE_LABELS).map(
  ([value, label]) => ({
    value,
    label,
  }),
);

interface DataSourceFormProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: CreateDataSourceRequest) => void;
  initialData?: DataSource;
  loading?: boolean;
}

export function DataSourceForm({
  open,
  onClose,
  onSubmit,
  initialData,
  loading = false,
}: DataSourceFormProps) {
  const isEdit = !!initialData;

  const [name, setName] = useState("");
  const [type, setType] = useState<DataSourceType>("database");
  const [authType, setAuthType] = useState<AuthType>("none");
  const [connectionConfig, setConnectionConfig] = useState<
    Record<string, unknown>
  >({});
  const [syncMode, setSyncMode] = useState<SyncMode>("manual");
  const [description, setDescription] = useState("");

  // Reset form when modal opens or initialData changes
  useEffect(() => {
    if (open) {
      if (initialData) {
        setName(initialData.name);
        setType(initialData.type);
        setAuthType(initialData.authType);
        setConnectionConfig(initialData.connectionConfig ?? {});
        setSyncMode(initialData.syncMode);
        setDescription(initialData.description ?? "");
      } else {
        setName("");
        setType("database");
        setAuthType("none");
        setConnectionConfig({});
        setSyncMode("manual");
        setDescription("");
      }
    }
  }, [open, initialData]);

  const handleSubmit = () => {
    if (!name.trim()) return;
    onSubmit({
      name: name.trim(),
      description,
      type,
      connectionConfig,
      authType,
      syncMode,
    });
  };

  const isValid = name.trim().length > 0;

  // Render connection config based on type
  const renderConnectionConfig = () => {
    switch (type) {
      case "database":
        return (
          <DatabaseConfigForm
            config={connectionConfig}
            onChange={setConnectionConfig}
          />
        );
      case "api":
        return (
          <ApiConfigForm
            config={connectionConfig}
            onChange={setConnectionConfig}
          />
        );
      case "file":
        return (
          <FileConfigForm
            config={connectionConfig}
            onChange={setConnectionConfig}
          />
        );
      case "gis":
        return (
          <GisConfigForm
            config={connectionConfig}
            onChange={setConnectionConfig}
          />
        );
      default:
        return null;
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="bg-background relative w-full max-w-lg overflow-hidden rounded-2xl shadow-xl"
          >
            {/* Header */}
            <div className="border-border bg-muted/50 flex items-center gap-3 border-b px-6 py-4">
              <div className="border-primary/20 bg-primary/10 text-primary flex h-10 w-10 items-center justify-center rounded-lg border">
                <Database className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-foreground text-lg leading-tight font-semibold">
                  {isEdit ? "编辑数据源" : "添加数据源"}
                </h3>
                <div className="text-muted-foreground text-xs">
                  {isEdit ? "修改数据源配置信息" : "配置新的数据源连接"}
                </div>
              </div>
            </div>

            {/* Body */}
            <div className="max-h-[60vh] space-y-5 overflow-y-auto p-6">
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  名称 <span className="text-destructive">*</span>
                </label>
                <Input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如：生产数据库"
                  className="w-full"
                />
              </div>

              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  描述{" "}
                  <span className="text-muted-foreground text-xs font-normal">
                    (给 AI:这个数据源里是什么)
                  </span>
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="例如:厂界噪声 2024 年监测值"
                  rows={2}
                  className="border-input bg-background focus-visible:ring-ring w-full resize-none rounded-lg border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
                />
              </div>

              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  数据源类型
                </label>
                <CustomSelect
                  value={type}
                  onChange={(v) => {
                    setType(v as DataSourceType);
                    setConnectionConfig({});
                  }}
                  options={TYPE_OPTIONS}
                />
              </div>

              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  认证方式
                </label>
                <CustomSelect
                  value={authType}
                  onChange={(v) => setAuthType(v as AuthType)}
                  options={AUTH_TYPE_OPTIONS}
                />
              </div>

              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  连接配置
                </label>
                {renderConnectionConfig()}
              </div>

              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  同步模式
                </label>
                <CustomSelect
                  value={syncMode}
                  onChange={(v) => setSyncMode(v as SyncMode)}
                  options={SYNC_MODE_OPTIONS}
                />
              </div>
            </div>

            {/* Footer */}
            <div className="border-border bg-muted/50 flex items-center justify-end gap-3 border-t px-6 py-4">
              <Button variant="outline" onClick={onClose}>
                取消
              </Button>
              <Button onClick={handleSubmit} disabled={!isValid || loading}>
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                {isEdit ? "保存" : "创建"}
              </Button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
