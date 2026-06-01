"use client";

import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";
import { fetch as fetchWithAuth } from "@/core/api/fetcher";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  (typeof window !== "undefined" && window.location.port === "4000"
    ? "http://localhost:8001"
    : "/api");

function getBaseUrl(): string {
  if (API_BASE.startsWith("http")) return API_BASE;
  return `${window.location.origin}${API_BASE}`;
}

export function createCollabAITransport(): ChatTransport<UIMessage> {
  return {
    async sendMessages(options): Promise<ReadableStream<UIMessageChunk>> {
      const { messages, abortSignal } = options;
      const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
      const userText = lastUserMsg?.parts
        ?.filter((p): p is { type: "text"; text: string } => p.type === "text")
        .map((p) => p.text)
        .join("") ?? "";

      const operation = mapPromptToOperation(userText);

      const res = await fetchWithAuth(`${getBaseUrl()}/extensions/docmgr/documents/ai-edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: userText, operation }),
        signal: abortSignal,
      });

      if (!res.ok) {
        const errorText = await res.text().catch(() => res.statusText);
        throw new Error(`AI request failed: ${res.status} ${errorText}`);
      }

      const data = (await res.json()) as { result: string };
      const resultText = data.result || "";

      return new ReadableStream<UIMessageChunk>({
        start(controller) {
          const id = crypto.randomUUID();
          controller.enqueue({ type: "text-start", id });
          controller.enqueue({ type: "text-delta", id, delta: resultText });
          controller.enqueue({ type: "text-end", id });
          controller.close();
        },
      });
    },

    async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
      return null;
    },
  };
}

function mapPromptToOperation(prompt: string): string {
  const lower = prompt.toLowerCase();
  if (lower.includes("润色") || lower.includes("polish") || lower.includes("improve")) return "polish";
  if (lower.includes("扩写") || lower.includes("expand") || lower.includes("elaborate")) return "expand";
  if (lower.includes("精简") || lower.includes("condense") || lower.includes("shorten") || lower.includes("summarize"))
    return "condense";
  if (lower.includes("头脑风暴") || lower.includes("brainstorm") || lower.includes("ideas")) return "brainstorm";
  return "polish";
}
