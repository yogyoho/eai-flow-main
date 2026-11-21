"use client";

import type { ReactNode } from "react";

import { Overlay } from "@/extensions/bid-write/components/primitives";

/** bid-write 帮助说明的通用弹窗骨架；页面内容由 children 提供。 */
export function HelpDrawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <Overlay
      open={open}
      title={title}
      onClose={onClose}
      variant="modal"
      size="wide"
      footer={
        <button type="button" className="btn pri" onClick={onClose}>
          知道了
        </button>
      }
    >
      {children}
    </Overlay>
  );
}
