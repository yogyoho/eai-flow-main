"use client";

// EAI-CUSTOM: client layout 不可导出 metadata，挂载时设置浏览器标签页标题
import { useEffect } from "react";

export default function Metadata() {
  useEffect(() => {
    document.title = "文档资产库 EN/FR 文档 · 中文译本对照管理";
  }, []);
  return null;
}
