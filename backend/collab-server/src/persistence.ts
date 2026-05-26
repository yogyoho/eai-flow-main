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

export async function canAccessDocument(userId: string, docId: string): Promise<boolean> {
  const result = await pool.query(
    `SELECT 1 FROM ai_documents d
     LEFT JOIN project_members pm ON d.project_id = pm.project_id
     WHERE d.id = $1 AND (d.user_id = $2 OR pm.user_id = $2)
     LIMIT 1`,
    [docId, userId],
  );
  return result.rows.length > 0;
}
