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
): Promise<number> {
  const result = await pool.query(
    `INSERT INTO collab_versions (doc_id, version, snapshot, summary, created_by, created_at)
     SELECT $1, COALESCE(MAX(v.version), 0) + 1, $2, $3, $4, NOW()
     FROM collab_versions v WHERE v.doc_id = $1
     RETURNING version`,
    [docId, Buffer.from(snapshot), summary || null, userId],
  );
  return result.rows[0]?.version || 1;
}

export async function canAccessDocument(userId: string, docId: string): Promise<boolean> {
  // 1. User is the document owner
  const ownerCheck = await pool.query(
    "SELECT 1 FROM ai_documents WHERE id = $1 AND user_id = $2",
    [docId, userId],
  );
  if (ownerCheck.rows.length > 0) return true;

  // 2. Document belongs to a project where user is a member
  const memberCheck = await pool.query(
    `SELECT 1 FROM ai_documents d
     JOIN project_members pm ON d.project_id = pm.project_id
     WHERE d.id = $1 AND pm.user_id = $2`,
    [docId, userId],
  );
  return memberCheck.rows.length > 0;
}
