"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { ShellLayout } from "@/extensions/shell";
import { ApprovalFlowEditor } from "@/extensions/project/ApprovalFlowEditor";

export default function ApprovalSettingsPage() {
  return (
    <ShellLayout>
      <div className="flex h-full flex-col">
        <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
          <Link href="/projects">
            <Button variant="ghost" size="icon" className="h-8 w-8 mr-2">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="text-[15px] font-semibold text-[#0F172A]">审批流程设置</h1>
        </header>
        <div className="flex-1 overflow-auto">
          <ApprovalFlowEditor />
        </div>
      </div>
    </ShellLayout>
  );
}
