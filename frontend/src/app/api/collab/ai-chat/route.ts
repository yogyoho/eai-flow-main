const OPENAI_BASE_URL =
  process.env.COLLAB_AI_BASE_URL || "https://api.deepseek.com/v1";
const OPENAI_API_KEY =
  process.env.COLLAB_AI_API_KEY ||
  process.env.DEEPSEEK_API_KEY ||
  process.env.ZHIPU_API_KEY ||
  "";
const MODEL_NAME = process.env.COLLAB_AI_MODEL || "deepseek-chat";

function stripHtml(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<\/h[1-6]>/gi, "\n")
    .replace(/<\/li>/gi, "\n")
    .replace(/<\/tr>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
}

function toChatMessages(
  raw: unknown[],
  hasTools: boolean,
): ChatMessage[] {
  const systemContent = hasTools
    ? "You are an AI writing assistant embedded in a block-based document editor.\n" +
      "You MUST use the applyDocumentOperations tool to modify the document.\n" +
      "Rules:\n" +
      "- When asked to modify/translate/polish/expand/condense text, call applyDocumentOperations with update operations.\n" +
      "- The `id` field in each operation MUST exactly match the block id from <selected-text>.\n" +
      "- The `block` field MUST be a valid HTML element (e.g. <p>text</p> or <h2>text</h2>).\n" +
      "- Do NOT output any explanatory text. Call the tool directly.\n" +
      "- Always respond in the same language as the user's input."
    : "你是一个嵌入在文档编辑器中的AI写作助手。\n" +
      "当用户要求修改文本时，只输出修改后的文本，不要任何解释或前缀。\n" +
      "当用户要求头脑风暴时，输出清晰的列表。\n" +
      "始终使用与用户输入相同的语言回复。";

  const result: ChatMessage[] = [{ role: "system", content: systemContent }];
  const msgs = raw as Array<Record<string, unknown>>;

  for (let i = 0; i < msgs.length; i++) {
    const msg = msgs[i];
    let role = String(msg.role ?? "user");
    if (role === "developer") role = "system";
    if (!["system", "user", "assistant"].includes(role)) role = "user";

    let content = "";
    if (typeof msg.content === "string") {
      content = msg.content;
    } else if (Array.isArray(msg.parts)) {
      content = (msg.parts as Array<Record<string, unknown>>)
        .filter((p) => p.type === "text")
        .map((p) => String(p.text ?? ""))
        .join("\n");
    } else if (msg.content) {
      content = JSON.stringify(msg.content);
    }

    if (role === "user" && i === msgs.length - 1) {
      const meta = msg.metadata as Record<string, unknown> | undefined;
      const docState = meta?.documentState as
        | Record<string, unknown>
        | undefined;
      const blocks = docState?.selectedBlocks as
        | Array<Record<string, unknown>>
        | undefined;
      if (Array.isArray(blocks) && blocks.length > 0) {
        const blockInfo = blocks
          .map((b) => {
            const html = String(b.block ?? "");
            const text = stripHtml(html);
            return `Block ID: ${b.id}\nHTML: ${html}\nText: ${text}`;
          })
          .join("\n\n");
        if (blockInfo) {
          content += `\n\nThe following blocks are selected in the document. Use their exact block IDs in the applyDocumentOperations tool:\n<selected-text>\n${blockInfo}\n</selected-text>`;
        }
      }
    }

    result.push({ role: role as ChatMessage["role"], content });
  }
  return result;
}

function toOpenAITools(toolDefinitions: Record<string, unknown> | undefined) {
  if (!toolDefinitions || typeof toolDefinitions !== "object") return undefined;
  const functions: Array<{
    type: "function";
    function: { name: string; parameters: unknown };
  }> = [];
  for (const [name, def] of Object.entries(toolDefinitions)) {
    const defObj = def as Record<string, unknown>;
    if (defObj.inputSchema) {
      functions.push({
        type: "function",
        function: { name, parameters: defObj.inputSchema },
      });
    }
  }
  return functions.length > 0 ? functions : undefined;
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { messages, toolDefinitions } = body;
    const tools = toOpenAITools(toolDefinitions);
    const hasTools = !!tools;
    const chatMessages = toChatMessages(messages, hasTools);

    const requestBody: Record<string, unknown> = {
      model: MODEL_NAME,
      messages: chatMessages,
      stream: true,
    };

    if (hasTools) {
      requestBody.tools = tools;
      requestBody.tool_choice = "auto";
    }

    const response = await fetch(`${OPENAI_BASE_URL}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${OPENAI_API_KEY}`,
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[ai-chat] LLM error:", response.status, errorText);
      return new Response(
        JSON.stringify({ error: `LLM error: ${response.status}` }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      );
    }

    if (!hasTools) {
      return streamTextResponse(response);
    }
    return streamToolResponse(response);
  } catch (error) {
    console.error("[ai-chat] Error:", error);
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Internal error",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}

/** Stream plain text deltas in AI SDK UI message format */
function streamTextResponse(upstream: Response): Response {
  const reader = upstream.body!.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const textId = `txt-${Date.now()}`;

  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(
        encoder.encode(`data: ${JSON.stringify({ type: "start" })}\n\n`),
      );
      controller.enqueue(
        encoder.encode(
          `data: ${JSON.stringify({ type: "text-start", id: textId })}\n\n`,
        ),
      );
      let buffer = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data: ")) continue;
            const data = trimmed.slice(6);
            if (data === "[DONE]") continue;

            try {
              const parsed = JSON.parse(data);
              const delta = parsed.choices?.[0]?.delta;
              if (delta?.content) {
                controller.enqueue(
                  encoder.encode(
                    `data: ${JSON.stringify({
                      type: "text-delta",
                      id: textId,
                      delta: delta.content,
                    })}\n\n`,
                  ),
                );
              }
            } catch {
              // Skip malformed chunks
            }
          }
        }
      } catch (error) {
        console.error("[ai-chat] Stream error:", error);
      }

      controller.enqueue(
        encoder.encode(
          `data: ${JSON.stringify({ type: "text-end", id: textId })}\n\n`,
        ),
      );
      controller.enqueue(
        encoder.encode(`data: ${JSON.stringify({ type: "finish" })}\n\n`),
      );
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

/**
 * Collect tool-call response from LLM and emit in AI SDK UI message
 * stream format using the correct chunk types:
 * - tool-input-start → tool-input-delta → tool-input-available (via streaming)
 */
function streamToolResponse(upstream: Response): Response {
  const reader = upstream.body!.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(
        encoder.encode(`data: ${JSON.stringify({ type: "start" })}\n\n`),
      );

      let toolCallId = "";
      let toolCallName = "";
      let toolCallArgs = "";
      const textId = `txt-${Date.now()}`;
      let textStarted = false;

      try {
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data: ")) continue;
            const data = trimmed.slice(6);
            if (data === "[DONE]") continue;

            try {
              const parsed = JSON.parse(data);
              const delta = parsed.choices?.[0]?.delta;

              // Stream any text content the LLM emits
              if (delta?.content) {
                if (!textStarted) {
                  textStarted = true;
                  controller.enqueue(
                    encoder.encode(
                      `data: ${JSON.stringify({ type: "text-start", id: textId })}\n\n`,
                    ),
                  );
                }
                controller.enqueue(
                  encoder.encode(
                    `data: ${JSON.stringify({
                      type: "text-delta",
                      id: textId,
                      delta: delta.content,
                    })}\n\n`,
                  ),
                );
              }

              // Collect tool calls from LLM
              if (delta?.tool_calls) {
                for (const tc of delta.tool_calls) {
                  if (tc.id) toolCallId = tc.id;
                  if (tc.function?.name) toolCallName = tc.function.name;
                  if (tc.function?.arguments)
                    toolCallArgs += tc.function.arguments;
                }
              }
            } catch {
              // Skip malformed chunks
            }
          }
        }
      } catch (error) {
        console.error("[ai-chat] Tool stream error:", error);
      }

      if (textStarted) {
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "text-end", id: textId })}\n\n`,
          ),
        );
      }

      // Emit tool call using correct AI SDK UI message stream format
      if (toolCallName && toolCallArgs) {
        let parsedArgs: unknown;
        try {
          parsedArgs = JSON.parse(toolCallArgs);
        } catch {
          parsedArgs = {};
        }

        const tcId = toolCallId || `call_${Date.now()}`;

        // tool-input-start: signal that a tool call is beginning
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({
              type: "tool-input-start",
              toolCallId: tcId,
              toolName: toolCallName,
            })}\n\n`,
          ),
        );

        // tool-input-available: provide the complete parsed input
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({
              type: "tool-input-available",
              toolCallId: tcId,
              toolName: toolCallName,
              input: parsedArgs,
            })}\n\n`,
          ),
        );
      }

      controller.enqueue(
        encoder.encode(`data: ${JSON.stringify({ type: "finish" })}\n\n`),
      );
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
