"use client";

import type { ReactNode } from "react";

import { ShellLayout } from "@/extensions/shell";

export default function CadDesignLayout({ children }: { children: ReactNode }) {
  return <ShellLayout>{children}</ShellLayout>;
}
