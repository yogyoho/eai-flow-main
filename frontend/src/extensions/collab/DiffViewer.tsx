"use client";

interface DiffViewerProps {
  fromVersion: number | null;
  toVersion: number | null;
}

export function DiffViewer({ fromVersion, toVersion }: DiffViewerProps) {
  return (
    <div className="p-4 text-center text-sm text-muted-foreground">
      <p>版本差异对比功能开发中</p>
      {fromVersion && toVersion && (
        <p className="mt-1 text-xs">
          对比 v{fromVersion} → v{toVersion}
        </p>
      )}
    </div>
  );
}
