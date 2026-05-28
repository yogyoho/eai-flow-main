"""Reset admin password in the gateway database."""
import base64
import hashlib
import bcrypt
import sqlite3

def pre_hash_v2(password):
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())

def make_hash(password):
    pre = pre_hash_v2(password)
    raw = bcrypt.hashpw(pre, bcrypt.gensalt()).decode("utf-8")
    return "$dfv2$" + raw

def verify(password, stored):
    prefix = "$dfv2$"
    bcrypt_hash = stored[len(prefix):]
    return bcrypt.checkpw(pre_hash_v2(password), bcrypt_hash.encode("utf-8"))

new_password = "Admin@2026"
new_hash = make_hash(new_password)
print(f"New hash: {new_hash}")

db_path = ".deer-flow/data/deerflow.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("UPDATE users SET password_hash = ? WHERE email = ?", (new_hash, "admin@eai-flow.com"))
print(f"Updated {cur.rowcount} row(s)")
conn.commit()

cur.execute("SELECT password_hash FROM users WHERE email = ?", ("admin@eai-flow.com",))
row = cur.fetchone()
stored = row[0]
print(f"Stored: {stored}")

result = verify(new_password, stored)
print(f"Verify: {result}")
conn.close()
