import type { Document } from "@hocuspocus/server";
import { Server } from "@hocuspocus/server";
import * as Y from "yjs";
import { authenticateConnection, validateOrigin } from "./auth.js";
import {
  canAccessDocument,
  createVersion,
  getDocumentVersion,
  loadDocument,
  loadMarkdownForDoc,
  pruneVersions,
  recordUpdate,
  storeDocument,
} from "./persistence.js";

const PORT = parseInt(process.env.COLLAB_PORT || "8002", 10);
const SNAPSHOT_INTERVAL_MS = parseInt(process.env.SNAPSHOT_INTERVAL_MS || "1800000", 10);

const activeDocuments = new Map<
  string,
  { doc: Document; lastSnapshotVersion: number; lastUserId: string }
>();

/**
 * Extract readable text from a Yjs document for diff/summary purposes.
 *
 * EAI-CUSTOM (bug B11 协同链审计): 客户端 BlockNote 协同挂载的是
 * `ydoc.getXmlFragment("document-store")`（BlockNoteEditor.tsx collaboration.fragment），
 * 旧实现读 `ydoc.getMap("blocks")` 恒为空 Map → snapshot_text 永远为空，
 * 版本 diff / AI 摘要功能整体不可用。改读 document-store XmlFragment，
 * 遍历 XmlElement 递归提取可读文本。
 */
export function extractTextFromYDoc(ydoc: Y.Doc): string {
  try {
    const fragment = ydoc.getXmlFragment("document-store");
    const lines: string[] = [];
    // yjs 13.6 的 XmlFragment/XmlElement 未实现 Symbol.iterator，用公开的 toArray()
    for (const child of fragment.toArray()) {
      if (child instanceof Y.XmlElement) {
        lines.push(extractXmlText(child));
      } else if (child instanceof Y.XmlText) {
        lines.push(child.toString());
      }
    }
    return lines.join("\n");
  } catch {
    return "";
  }
}

function extractXmlText(el: Y.XmlElement): string {
  const parts: string[] = [];
  for (const child of el.toArray()) {
    if (child instanceof Y.XmlText) {
      parts.push(child.toString());
    } else if (child instanceof Y.XmlElement) {
      parts.push(extractXmlText(child));
    }
  }
  return parts.join("");
}

/**
 * EAI-CUSTOM (bug B11 协同链审计): 周期/断开快照只增不删，collab_versions 已积累
 * 6493 行（单文档 5873）。每次 createVersion 后按 doc 裁剪，仅保留最近
 * MAX_VERSIONS_PER_DOC 条历史。失败不影响保存主流程，仅记日志。
 */
async function pruneVersionsSafe(docId: string): Promise<void> {
  try {
    const pruned = await pruneVersions(docId);
    if (pruned > 0) {
      console.log(`[versions] Pruned ${pruned} old version(s) for doc ${docId}`);
    }
  } catch (err) {
    console.error(`[versions] Prune failed for doc ${docId}:`, err);
  }
}

const server = Server.configure({
  port: PORT,

  async onConnect({ request, documentName, context }) {
    if (!validateOrigin(request)) {
      console.log("[onConnect] Forbidden: invalid origin");
      throw new Error("Forbidden: invalid origin");
    }

    const user = authenticateConnection(request);
    if (!user) {
      console.log("[onConnect] Unauthorized - no valid token");
      throw new Error("Unauthorized");
    }

    Object.assign(context, { userId: user.userId });

    const hasAccess = await canAccessDocument(user.userId, documentName);
    if (!hasAccess) {
      console.log(`[onConnect] Forbidden: userId=${user.userId} docId=${documentName}`);
      throw new Error("Forbidden: no access to this document");
    }
    console.log(`[onConnect] Connected: userId=${user.userId} docId=${documentName}`);
  },

  async onLoadDocument({ document, documentName }) {
    const existing = await loadDocument(documentName);
    if (existing) {
      Y.applyUpdate(document, existing);
    } else {
      // First open: load markdown from ai_documents and store in Yjs metadata
      // so the client can seed the BlockNote editor from it.
      const markdown = await loadMarkdownForDoc(documentName);
      if (markdown && markdown.trim()) {
        const meta = document.getMap("_collabMeta");
        meta.set("pendingMarkdown", markdown);
      }
    }

    const currentVer = await getDocumentVersion(documentName);
    if (!activeDocuments.has(documentName)) {
      activeDocuments.set(documentName, {
        doc: document,
        lastSnapshotVersion: currentVer,
        lastUserId: "unknown",
      });
    }
  },

  async onStoreDocument({ document, documentName, context }) {
    const state = Y.encodeStateAsUpdate(document);
    const userId = (context as { userId: string })?.userId || "unknown";
    await storeDocument(documentName, state, userId);
    await recordUpdate(documentName, state, userId, 0);

    const entry = activeDocuments.get(documentName);
    if (entry) {
      entry.lastUserId = userId;
    }
  },

  async onDisconnect({ document, documentName, context }) {
    const userId = (context as { userId: string })?.userId || "unknown";
    const state = Y.encodeStateAsUpdate(document);
    const snapshotText = extractTextFromYDoc(document);
    await createVersion(documentName, state, userId, "Auto-save on disconnect", snapshotText);
    await pruneVersionsSafe(documentName);

    if (activeDocuments.has(documentName)) {
      const connections = document.connections;
      if (!connections || connections.size === 0) {
        activeDocuments.delete(documentName);
      }
    }
  },

  async afterUnloadDocument({ documentName }: { documentName: string }) {
    activeDocuments.delete(documentName);
  },
});

async function periodicSnapshot() {
  if (activeDocuments.size === 0) return;

  console.log(`[snapshot] Checking ${activeDocuments.size} active document(s)...`);
  for (const [docId, entry] of activeDocuments) {
    try {
      const currentVer = await getDocumentVersion(docId);
      if (currentVer > entry.lastSnapshotVersion) {
        const state = Y.encodeStateAsUpdate(entry.doc);
        const snapshotText = extractTextFromYDoc(entry.doc);
        const version = await createVersion(docId, state, entry.lastUserId, "Auto-save (periodic)", snapshotText);
        entry.lastSnapshotVersion = version;
        await pruneVersionsSafe(docId);
        console.log(`[snapshot] Created version ${version} for doc ${docId}`);
      }
    } catch (err) {
      console.error(`[snapshot] Failed for doc ${docId}:`, err);
    }
  }
}

server.listen().then(() => {
  console.log(`Hocuspocus collaboration server running on port ${PORT}`);
  console.log(`[snapshot] Periodic snapshots every ${SNAPSHOT_INTERVAL_MS / 1000}s`);

  setInterval(periodicSnapshot, SNAPSHOT_INTERVAL_MS);
});
