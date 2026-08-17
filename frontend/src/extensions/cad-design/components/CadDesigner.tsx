"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";
import { MessageList } from "@/components/workspace/messages/message-list";
import { resolveArtifactURL } from "@/core/artifacts/utils";
import { useThreadStream } from "@/core/threads/hooks";
import type { AgentThreadState } from "@/core/threads/types";

// model-viewer is a web component — client-only to avoid Next SSR.
const ModelViewer = dynamic(() => import("./ModelViewer"), {
  ssr: false,
  loading: () => (
    <p className="text-muted-foreground p-4 text-sm">加载 3D 预览…</p>
  ),
});

interface ArtifactLike {
  filepath?: string;
}

const cadContext = {
  model_name: undefined,
  mode: "flash" as const,
  reasoning_effort: undefined,
};

export function CadDesigner() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [glbPath, setGlbPath] = useState<string | null>(null);
  const [stepPath, setStepPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setThreadId(crypto.randomUUID());
  }, []);

  const onFinish = useCallback((state: AgentThreadState) => {
    setBusy(false);
    const arts = (state.artifacts ?? []) as unknown as ArtifactLike[];
    // Pick the latest artifacts (multi-turn: later turns append)
    const glbArts = arts.filter((a) => a.filepath?.endsWith(".glb"));
    // EAI-CUSTOM: truthiness OR (not `??`) — `.some` keeps old `||` semantics where
    // a defined filepath that fails ".step" must still match ".stp"
    const stepArts = arts.filter((a) =>
      [".step", ".stp"].some((ext) => a.filepath?.endsWith(ext)),
    );
    const glb = glbArts.length
      ? (glbArts[glbArts.length - 1]!.filepath ?? null)
      : null;
    const step = stepArts.length
      ? (stepArts[stepArts.length - 1]!.filepath ?? null)
      : null;
    setGlbPath(glb);
    setStepPath(step);
    setStatus(glb || step ? "生成完成 ✓" : "完成，但未找到 STEP/GLB 产物");
  }, []);

  const { thread, sendMessage } = useThreadStream({
    threadId,
    onFinish,
    context: cadContext,
  });

  const handleSubmit = useCallback(
    async (message: PromptInputMessage) => {
      if (!threadId || !message.text.trim() || busy) return;
      setGlbPath(null);
      setStepPath(null);
      setError(null);
      setBusy(true);
      setStatus("生成中…（agent 编写 build123d 源码 → 导出 STEP/GLB）");
      try {
        await sendMessage(threadId, { text: message.text.trim(), files: [] });
      } catch (e) {
        setBusy(false);
        setError(`生成失败: ${(e as Error).message}`);
      }
    },
    [threadId, busy, sendMessage],
  );

  const glbUrl = useMemo(
    () => (glbPath && threadId ? resolveArtifactURL(glbPath, threadId) : null),
    [glbPath, threadId],
  );
  const stepUrl = useMemo(
    () =>
      stepPath && threadId
        ? `${resolveArtifactURL(stepPath, threadId)}?download=true`
        : null,
    [stepPath, threadId],
  );

  const chatStatus = busy ? ("submitted" as const) : ("ready" as const);

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="shrink-0 border-b px-6 py-3">
        <h1 className="text-lg font-bold">CAD 制图</h1>
        <p className="text-muted-foreground text-xs">
          描述零件（mm）→ AI 生成 STEP + 3D 预览 → 下载
        </p>
      </header>

      {/* Body: chat left, preview right */}
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_380px]">
        {/* LEFT: Chat */}
        <div className="flex min-h-0 flex-col border-r">
          <div className="min-h-0 flex-1 overflow-y-auto">
            <MessageList
              threadId={threadId ?? ""}
              thread={thread}
              tokenUsageInlineMode="off"
            />
          </div>
          <div className="shrink-0 border-t p-3">
            <PromptInput onSubmit={handleSubmit}>
              <PromptInputBody>
                <PromptInputTextarea placeholder="描述你要的零件（例：100×60×20mm 方块，顶部四角各一个 8mm 通孔）…" />
              </PromptInputBody>
              <PromptInputFooter>
                <PromptInputTools>
                  <PromptInputSubmit
                    status={chatStatus}
                    disabled={!threadId || busy}
                  />
                </PromptInputTools>
              </PromptInputFooter>
            </PromptInput>
          </div>
        </div>

        {/* RIGHT: 3D Preview + Downloads */}
        <div className="flex min-h-0 flex-col">
          <div className="min-h-[420px] flex-1">
            {glbUrl ? (
              <ModelViewer src={glbUrl} />
            ) : (
              <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
                {busy
                  ? "生成中…"
                  : "生成的零件 GLB 会在此 3D 预览（可旋转/缩放）"}
              </div>
            )}
          </div>
          <div className="shrink-0 border-t p-4">
            <h2 className="mb-2 text-sm font-medium">产物</h2>
            {stepUrl ? (
              <a
                href={stepUrl}
                className="text-primary text-sm underline"
                download
              >
                下载 STEP 文件
              </a>
            ) : (
              <p className="text-muted-foreground text-xs">
                生成后出现下载链接
              </p>
            )}
            {glbPath && (
              <p className="text-muted-foreground mt-2 text-xs break-all">
                GLB: {glbPath}
              </p>
            )}
            {status && (
              <p className="text-muted-foreground mt-2 text-xs">{status}</p>
            )}
            {error && <p className="text-destructive mt-2 text-xs">{error}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
