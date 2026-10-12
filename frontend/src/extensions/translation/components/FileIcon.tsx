"use client";

import { cn } from "@/lib/utils";

/** 仿 Windows 文件类型徽章：彩色圆角方块 + 白色类型字母（对齐文档空间文件图标风格）。 */

const TYPES: Record<string, { bg: string; letter: string }> = {
  docx: { bg: "#2B579A", letter: "W" },
  doc: { bg: "#2B579A", letter: "W" },
  xlsx: { bg: "#217346", letter: "X" },
  xlsm: { bg: "#217346", letter: "X" },
  csv: { bg: "#217346", letter: "X" },
  pptx: { bg: "#C43E1C", letter: "P" },
  ppt: { bg: "#C43E1C", letter: "P" },
  pdf: { bg: "#B30B00", letter: "A" },
  md: { bg: "#57606A", letter: "M" },
  txt: { bg: "#57606A", letter: "T" },
  png: { bg: "#7A5FB5", letter: "I" },
  jpg: { bg: "#7A5FB5", letter: "I" },
  jpeg: { bg: "#7A5FB5", letter: "I" },
  tif: { bg: "#7A5FB5", letter: "I" },
  tiff: { bg: "#7A5FB5", letter: "I" },
  bmp: { bg: "#7A5FB5", letter: "I" },
  gif: { bg: "#7A5FB5", letter: "I" },
};

export function FileIcon({
  name,
  className,
}: {
  name: string;
  className?: string;
}) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const t = TYPES[ext] ?? { bg: "#8A8F98", letter: "F" };
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] shadow-sm",
        className,
      )}
      style={{ backgroundColor: t.bg }}
    >
      <span className="text-[10px] font-bold leading-none text-white">{t.letter}</span>
    </span>
  );
}
