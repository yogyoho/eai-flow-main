"use client";

import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, CheckCircle2, RefreshCw, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { cn } from "@/lib/utils";

// ─── Toast ───────────────────────────────────────────────────────────────────

export type ToastType = "success" | "error" | "info";
export interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

export function ToastContainer({
  toasts,
  onRemove,
}: {
  toasts: Toast[];
  onRemove: (id: number) => void;
}) {
  return (
    <div className="pointer-events-none fixed right-6 bottom-6 z-[100] flex flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: 16, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className={cn(
              "pointer-events-auto flex items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium shadow-lg backdrop-blur-sm",
              t.type === "success" &&
                "border-green-200 bg-green-600 text-white",
              t.type === "error" && "border-red-200 bg-red-600 text-white",
              t.type === "info" && "border-blue-200 bg-blue-600 text-white",
            )}
          >
            {t.type === "success" && (
              <CheckCircle2 className="h-4 w-4 shrink-0" />
            )}
            {t.type === "error" && <AlertCircle className="h-4 w-4 shrink-0" />}
            {t.type === "info" && <RefreshCw className="h-4 w-4 shrink-0" />}
            <span>{t.message}</span>
            <button
              onClick={() => onRemove(t.id)}
              className="ml-1 opacity-60 transition-opacity hover:opacity-100"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const show = useCallback((message: string, type: ToastType = "info") => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(
      () => setToasts((prev) => prev.filter((t) => t.id !== id)),
      3500,
    );
  }, []);
  const remove = useCallback(
    (id: number) => setToasts((prev) => prev.filter((t) => t.id !== id)),
    [],
  );
  return { toasts, show, remove };
}
