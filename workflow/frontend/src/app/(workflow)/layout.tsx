"use client";

import { usePathname } from "next/navigation";
import { AppShell } from "@/components/app-shell";

export default function WorkflowLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname().replace(/^\/workflow(?=\/|$)/, "");
  if (pathname.startsWith("/design")) {
    return <>{children}</>;
  }
  return <AppShell>{children}</AppShell>;
}
