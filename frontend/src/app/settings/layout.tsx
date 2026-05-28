"use client";

import type { ReactNode } from "react";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <SimpleShellLayout>
      {children}
    </SimpleShellLayout>
  );
}
