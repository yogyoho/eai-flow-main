import { Hocuspocus, Server } from "@hocuspocus/server";
import * as Y from "yjs";
import { authenticateConnection } from "./auth.js";
import { loadDocument, storeDocument, canAccessDocument } from "./persistence.js";

const PORT = parseInt(process.env.COLLAB_PORT || "8002", 10);

const server = Server.configure({
  port: PORT,

  async onConnect({ connection }) {
    const user = authenticateConnection(connection.request);
    if (!user) {
      throw new Error("Unauthorized");
    }

    connection.context = { userId: user.userId };

    const docId = connection.documentName;
    const hasAccess = await canAccessDocument(user.userId, docId);
    if (!hasAccess) {
      throw new Error("Forbidden: no access to this document");
    }
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
  },
});

server.listen().then(() => {
  console.log(`Hocuspocus collaboration server running on port ${PORT}`);
});
