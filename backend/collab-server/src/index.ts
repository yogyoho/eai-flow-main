import { Server } from "@hocuspocus/server";
import * as Y from "yjs";
import { authenticateConnection, validateOrigin } from "./auth.js";
import { loadDocument, storeDocument, canAccessDocument, recordUpdate, createVersion } from "./persistence.js";

const PORT = parseInt(process.env.COLLAB_PORT || "8002", 10);

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
    }
  },

  async onStoreDocument({ document, documentName, context }) {
    const state = Y.encodeStateAsUpdate(document);
    const userId = (context as { userId: string })?.userId || "unknown";
    await storeDocument(documentName, state, userId);
    await recordUpdate(documentName, state, userId, 0);
  },

  async onDisconnect({ document, documentName, context }) {
    const userId = (context as { userId: string })?.userId || "unknown";
    const state = Y.encodeStateAsUpdate(document);
    await createVersion(documentName, state, userId, "Auto-save on disconnect");
  },
});

server.listen().then(() => {
  console.log(`Hocuspocus collaboration server running on port ${PORT}`);
});

const SNAPSHOT_INTERVAL_MS = parseInt(process.env.SNAPSHOT_INTERVAL_MS || "1800000", 10);
setInterval(() => {
  console.log("[snapshot] Periodic snapshot check running...");
}, SNAPSHOT_INTERVAL_MS);
