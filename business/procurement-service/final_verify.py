"""Final procurement integration verification"""
import httpx

BASE = "http://localhost:4026"

resp = httpx.post(f"{BASE}/api/extensions/auth/login", json={"username": "admin", "password": "admin123"}, timeout=10)
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

endpoints = [
    "/procurement/api/v1/experts",
    "/procurement/api/v1/experts/draws",
    "/procurement/api/v1/bidders",
    "/procurement/api/v1/plans",
    "/procurement/api/v1/projects",
    "/procurement/api/v1/bids",
    "/procurement/api/v1/evaluations",
    "/procurement/api/v1/winning-bids",
    "/procurement/api/v1/contracts",
    "/procurement/api/v1/complaints",
    "/procurement/api/v1/witness-records",
    "/procurement/api/v1/venue-spaces",
    "/procurement/api/v1/dashboard/stats",
    "/procurement/health",
    "/procurement/docs",
]

print(f"{'Endpoint':<45} {'Status':>6} {'Result'}")
print("-" * 90)
for ep in endpoints:
    try:
        r = httpx.get(f"{BASE}{ep}", headers=headers, timeout=10)
        status = r.status_code
        body = r.text[:80].replace("\n", " ")
        if status == 200:
            print(f"{ep:<45} {status:>6}  {body}")
        else:
            print(f"{ep:<45} {status:>6}  {body}")
    except Exception as e:
        print(f"{ep:<45} ERROR   {e}")
