"use client";

import { type ReactNode } from "react";

import { ShellLayout } from "@/extensions/shell";

interface SimpleShellLayoutProps {
  children: ReactNode;
}

export default function SimpleShellLayout({ children }: SimpleShellLayoutProps) {
  return <ShellLayout>{children}</ShellLayout>;
}
