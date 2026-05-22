"use client";

import { ChevronDown, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import React, { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

interface PluginConfigFormProps {
  schema: Record<string, unknown>;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
}

interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  minimum?: number;
  maximum?: number;
  pattern?: string;
  minLength?: number;
  maxLength?: number;
}

function getProperties(schema: Record<string, unknown>): Record<string, JsonSchemaProperty> {
  const props = (schema.properties ?? {}) as Record<string, Record<string, unknown>>;
  const result: Record<string, JsonSchemaProperty> = {};
  for (const [key, prop] of Object.entries(props)) {
    result[key] = {
      type: (prop.type as string) ?? "string",
      title: (prop.title as string) ?? key,
      description: (prop.description as string) ?? "",
      default: prop.default,
      enum: prop.enum as string[] | undefined,
      minimum: prop.minimum as number | undefined,
      maximum: prop.maximum as number | undefined,
      pattern: prop.pattern as string | undefined,
      minLength: prop.minLength as number | undefined,
      maxLength: prop.maxLength as number | undefined,
    };
  }
  return result;
}

function getRequiredList(schema: Record<string, unknown>): string[] {
  return (schema.required as string[]) ?? [];
}

/** CustomSelect - reuses the knowledge page pattern */
interface SelectOption {
  value: string;
  label: string;
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
          "border bg-background transition-all duration-150",
          open
            ? "border-primary shadow-sm ring-2 ring-ring/50"
            : "border-input hover:border-input hover:shadow-sm",
        )}
      >
        <span
          className={cn(
            "flex min-w-0 items-center gap-2",
            selected ? "text-foreground" : "text-muted-foreground",
          )}
        >
          <span className="truncate">{selected?.label ?? "请选择"}</span>
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
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
            className="absolute top-full right-0 left-0 z-50 mt-1.5 overflow-hidden rounded-xl border border-border bg-background shadow-lg shadow-black/5"
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
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-foreground hover:bg-muted",
                )}
              >
                {o.label}
                {o.value === value && (
                  <CheckCircle2 className="ml-auto h-3.5 w-3.5 shrink-0 text-primary" />
                )}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function PluginConfigForm({
  schema,
  values,
  onChange,
}: PluginConfigFormProps) {
  const properties = getProperties(schema);
  const required = getRequiredList(schema);

  const handleChange = (key: string, value: unknown) => {
    onChange({ ...values, [key]: value });
  };

  const entries = Object.entries(properties);
  if (entries.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        该插件无可配置项
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {entries.map(([key, prop]) => {
        const isRequired = required.includes(key);
        const currentValue = values[key] ?? prop.default ?? "";

        // Enum -> CustomSelect
        if (prop.enum && prop.enum.length > 0) {
          return (
            <div key={key}>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {prop.title} {isRequired && <span className="text-destructive">*</span>}
              </label>
              {prop.description && (
                <p className="mb-2 text-xs text-muted-foreground">{prop.description}</p>
              )}
              <CustomSelect
                value={String(currentValue)}
                onChange={(v) => handleChange(key, v)}
                options={prop.enum.map((e) => ({ value: e, label: e }))}
              />
            </div>
          );
        }

        // Boolean -> Switch
        if (prop.type === "boolean") {
          return (
            <div key={key} className="flex items-center justify-between rounded-lg border border-border bg-background p-4">
              <div>
                <label className="text-sm font-medium text-foreground">
                  {prop.title} {isRequired && <span className="text-destructive">*</span>}
                </label>
                {prop.description && (
                  <p className="mt-0.5 text-xs text-muted-foreground">{prop.description}</p>
                )}
              </div>
              <Switch
                checked={Boolean(currentValue)}
                onCheckedChange={(checked) => handleChange(key, checked)}
              />
            </div>
          );
        }

        // Number -> Input type=number
        if (prop.type === "number" || prop.type === "integer") {
          return (
            <div key={key}>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {prop.title} {isRequired && <span className="text-destructive">*</span>}
              </label>
              {prop.description && (
                <p className="mb-2 text-xs text-muted-foreground">{prop.description}</p>
              )}
              <Input
                type="number"
                value={String(currentValue)}
                onChange={(e) => handleChange(key, Number(e.target.value))}
                min={prop.minimum}
                max={prop.maximum}
                placeholder={`请输入${prop.title}`}
              />
            </div>
          );
        }

        // String -> Input
        return (
          <div key={key}>
            <label className="mb-1 block text-sm font-medium text-foreground">
              {prop.title} {isRequired && <span className="text-destructive">*</span>}
            </label>
            {prop.description && (
              <p className="mb-2 text-xs text-muted-foreground">{prop.description}</p>
            )}
            <Input
              type="text"
              value={String(currentValue)}
              onChange={(e) => handleChange(key, e.target.value)}
              placeholder={`请输入${prop.title}`}
              minLength={prop.minLength}
              maxLength={prop.maxLength}
              pattern={prop.pattern}
            />
          </div>
        );
      })}
    </div>
  );
}
