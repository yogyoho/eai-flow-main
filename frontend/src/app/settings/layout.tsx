"use client";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
import type { ReactNode } from "react";

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <SimpleShellLayout>
      {children}
    </SimpleShellLayout>
  );
}
