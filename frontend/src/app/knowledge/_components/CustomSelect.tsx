"use client";

import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, ChevronDown } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface SelectOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
  desc?: string;
}

export function CustomSelect({
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
                <span className="flex min-w-0 flex-col">
                  <span className="truncate">{o.label}</span>
                  {o.desc && (
                    <span className="text-muted-foreground mt-0.5 text-xs">
                      {o.desc}
                    </span>
                  )}
                </span>
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
