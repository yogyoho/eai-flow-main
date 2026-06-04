import pg from "pg";

const { Pool } = pg;

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

export async function loadDocument(docId: string): Promise<Uint8Array | null> {
  const result = await pool.query(
    "SELECT yjs_doc FROM collab_documents WHERE doc_id = $1",
    [docId],
  );
  if (result.rows.length === 0) return null;
  return new Uint8Array(result.rows[0].yjs_doc);
}

export async function storeDocument(
  docId: string,
  yjsDoc: Uint8Array,
  userId: string,
): Promise<void> {
  await pool.query(
    `INSERT INTO collab_documents (doc_id, yjs_doc, version, last_editor_id, updated_at)
     VALUES ($1, $2, 1, $3, NOW())
     ON CONFLICT (doc_id) DO UPDATE
     SET yjs_doc = $2, version = collab_documents.version + 1,
         last_editor_id = $3, updated_at = NOW()`,
    [docId, Buffer.from(yjsDoc), userId],
  );
}

export async function recordUpdate(
  docId: string,
  updateData: Uint8Array,
  userId: string,
  version: number,
): Promise<void> {
  await pool.query(
    `INSERT INTO collab_updates (doc_id, update_data, user_id, version, created_at)
     VALUES ($1, $2, $3, $4, NOW())`,
    [docId, Buffer.from(updateData), userId, version],
  );
}

export async function createVersion(
  docId: string,
  snapshot: Uint8Array,
  userId: string,
  summary?: string,
  snapshotText?: string,
): Promise<number> {
  const result = await pool.query(
    `INSERT INTO collab_versions (doc_id, version, snapshot, snapshot_text, summary, created_by, created_at)
     SELECT $1, COALESCE(MAX(v.version), 0) + 1, $2, $3, $4, $5, NOW()
     FROM collab_versions v WHERE v.doc_id = $1
     RETURNING version`,
    [docId, Buffer.from(snapshot), snapshotText || null, summary || null, userId],
  );
  return result.rows[0]?.version || 1;
}

export async function getDocumentVersion(docId: string): Promise<number> {
  const result = await pool.query(
    "SELECT version FROM collab_documents WHERE doc_id = $1",
    [docId],
  );
  return result.rows[0]?.version || 0;
}

export async function loadMarkdownForDoc(docId: string): Promise<string | null> {
  const result = await pool.query(
    "SELECT content, doc_type, file_ref_path FROM ai_documents WHERE id = $1",
    [docId],
  );
  if (result.rows.length === 0) return null;
  const row = result.rows[0];

  if (row.content) return row.content;

  if (row.doc_type === "file_ref" && row.file_ref_path) {
    try {
      const fs = await import("fs");
      if (fs.existsSync(row.file_ref_path)) {
        const stat = fs.statSync(row.file_ref_path);
        if (stat.size <= 10 * 1024 * 1024) {
          return fs.readFileSync(row.file_ref_path, "utf-8");
        }
      }
    } catch { /* file missing or unreadable */ }
  }

  return null;
}

export async function hasCollabData(docId: string): Promise<boolean> {
  const result = await pool.query(
    "SELECT 1 FROM collab_documents WHERE doc_id = $1",
    [docId],
  );
  return result.rows.length > 0;
}

export async function canAccessDocument(userId: string, docId: string): Promise<boolean> {
  // The userId comes from Gateway Auth JWT (sub field) and is the Gateway's internal user ID,
  // which differs from the Extensions PostgreSQL user ID. We resolve by:
  // 1. Direct match (same user ID in both systems)
  // 2. Email bridge: query Gateway API to get email, then look up extensions user by email

  // 1. Direct match
  const ownerCheck = await pool.query(
    "SELECT 1 FROM ai_documents WHERE id = $1 AND user_id = $2",
    [docId, userId],
  );
  if (ownerCheck.rows.length > 0) return true;

  const memberCheck = await pool.query(
    `SELECT 1 FROM ai_documents d
     JOIN project_members pm ON d.project_id = pm.project_id
     WHERE d.id = $1 AND pm.user_id = $2`,
    [docId, userId],
  );
  if (memberCheck.rows.length > 0) return true;

  // 2. Bridge via email: call Gateway's session endpoint to get email for the gateway user
  const extUserId = await bridgeGatewayUser(userId);
  if (extUserId && extUserId !== userId) {
    const owner2 = await pool.query(
      "SELECT 1 FROM ai_documents WHERE id = $1 AND user_id = $2",
      [docId, extUserId],
    );
    if (owner2.rows.length > 0) return true;

    const member2 = await pool.query(
      `SELECT 1 FROM ai_documents d
       JOIN project_members pm ON d.project_id = pm.project_id
       WHERE d.id = $1 AND pm.user_id = $2`,
      [docId, extUserId],
    );
    if (member2.rows.length > 0) return true;
  }

  return false;
}

async function bridgeGatewayUser(gatewayUserId: string): Promise<string | null> {
  try {
    const gatewayUrl = process.env.GATEWAY_URL || "http://gateway:8001";
    const resp = await fetch(`${gatewayUrl}/api/v1/auth/users/${gatewayUserId}`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!resp.ok) return null;
    const gwUser = (await resp.json()) as { email?: string };
    if (!gwUser.email) return null;

    const result = await pool.query(
      "SELECT id FROM users WHERE email = $1 AND is_deleted = false",
      [gwUser.email],
    );
    return result.rows[0]?.id || null;
  } catch {
    return null;
  }
}
