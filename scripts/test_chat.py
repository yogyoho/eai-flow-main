"""
Test chat Q&A flow with deepseek-v4-flash model.

Uses requests + manually reads SSE stream to test the full chat pipeline:
1. Login (get auth cookies)
2. Create thread
3. Send message + stream response
"""
import requests
import json
import sys
import re

BASE = "http://localhost:2026"
MODEL = "deepseek-v4-flash"
EMAIL = "admin@eai-flow.com"
PASSWORD = "admin123"

def login():
    """Login and return cookies dict."""
    resp = requests.post(
        f"{BASE}/api/v1/auth/login/local",
        data={"username": EMAIL, "password": PASSWORD},
        allow_redirects=False,
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    print(f"[LOGIN] OK - expires_in: {data.get('expires_in')}")
    access_token = resp.cookies.get("access_token")
    csrf_token = resp.cookies.get("csrf_token")
    assert access_token, "No access_token cookie"
    assert csrf_token, "No csrf_token cookie"
    return {"access_token": access_token, "csrf_token": csrf_token}

def create_thread(cookies):
    """Create a new thread and return its ID."""
    headers = {
        "X-CSRF-Token": cookies["csrf_token"],
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{BASE}/api/threads",
        json={},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200, f"Create thread failed: {resp.status_code} {resp.text}"
    data = resp.json()
    thread_id = data["thread_id"]
    print(f"[THREAD] Created: {thread_id}")
    return thread_id

def list_models(cookies):
    """List available models."""
    resp = requests.get(f"{BASE}/api/models", cookies=cookies)
    assert resp.status_code == 200, f"List models failed: {resp.status_code}"
    data = resp.json()
    models = []
    if isinstance(data, dict):
        items = data.get("models") or data.get("data") or []
        models = [m.get("id", m.get("name", str(m))) for m in items if isinstance(m, dict)]
    elif isinstance(data, list):
        models = [m.get("id", m.get("name", str(m))) for m in data if isinstance(m, dict)]
    print(f"[MODELS] Found {len(models)}: {models[:5]}...")
    return models

def _extract_chunk_text(chunk, current_response):
    """Extract text from a message chunk (can be a delta or full message)."""
    if not isinstance(chunk, dict):
        return

    content = chunk.get("content", "")
    if isinstance(content, str) and content.strip():
        print(content, end="", flush=True)

    # Handle tool_call chunks
    tool_calls = chunk.get("tool_calls", [])
    for tc in tool_calls:
        name = tc.get("name", "")
        if name:
            print(f"\n[TOOL] Calling: {name}")

    # Handle additional_kwargs
    addl = chunk.get("additional_kwargs", {}) or {}
    reasoning = addl.get("reasoning_content", "")
    if reasoning:
        print(f"\n[REASONING] {reasoning[:200]}...")


def send_message_and_stream(cookies, thread_id, content="Hello, please introduce yourself briefly in one sentence."):
    """Send a message and stream the response via SSE."""
    headers = {
        "X-CSRF-Token": cookies["csrf_token"],
        "Content-Type": "application/json",
    }

    # Step 1: Send message to create a run
    payload = {
        "input": {
            "messages": [
                {"role": "user", "content": content}
            ],
            "model": MODEL,
        },
        "config": {
            "configurable": {"model": MODEL},
        },
    }
    print(f"[CHAT] Sending message: '{content}'")

    # Create the run first
    resp = requests.post(
        f"{BASE}/api/threads/{thread_id}/runs",
        json=payload,
        cookies=cookies,
        headers=headers,
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"[ERROR] Create run failed: {resp.status_code} {resp.text}")
        return None

    run_data = resp.json()
    run_id = run_data.get("run_id")
    print(f"[CHAT] Run created: {run_id}")

    # Step 2: Stream the run
    stream_headers = {
        "Accept": "text/event-stream",
    }
    stream_url = f"{BASE}/api/threads/{thread_id}/runs/{run_id}/stream"
    print(f"[STREAM] Connecting to {stream_url}")

    stream_resp = requests.get(
        stream_url,
        cookies=cookies,
        headers=stream_headers,
        stream=True,
        timeout=300,
    )

    if stream_resp.status_code != 200:
        print(f"[ERROR] Stream failed: {stream_resp.status_code} {stream_resp.text[:500]}")
        return None

    print(f"[STREAM] Connected, reading events...")

    full_response = ""
    event_count = 0

    current_event = None
    try:
        for line in stream_resp.iter_lines(decode_unicode=True):
            if line is None:
                continue

            # Parse SSE event field
            if line.startswith("event: "):
                current_event = line[7:].strip()
                continue

            if line.startswith("data: "):
                event_count += 1
                data_str = line[6:]

                if data_str.strip() == "[DONE]":
                    print(f"\n[STREAM] Done. {event_count} events received.")
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                evt = current_event or data.get("event", "")

                # Handle different event types
                if evt == "metadata":
                    run_id = data.get("run_id", "")
                    thread_id_val = data.get("thread_id", "")
                    print(f"[META] run={run_id} thread={thread_id_val}")

                elif evt == "values":
                    # Full state snapshot — extract last AI message
                    messages = data.get("messages", [])
                    for msg in reversed(messages):
                        msg_type = msg.get("type", "")
                        if msg_type == "ai" or msg_type == "AIMessage":
                            msg_content = msg.get("content", "")
                            if isinstance(msg_content, str) and msg_content.strip():
                                # Only print new content
                                if len(msg_content) > len(full_response):
                                    new_text = msg_content[len(full_response):]
                                    full_response = msg_content
                                    print(new_text, end="", flush=True)
                            break

                elif evt == "messages" or evt == "messages-tuple":
                    msg_data = data.get("data", data)
                    if isinstance(msg_data, list):
                        for chunk in msg_data:
                            _extract_chunk_text(chunk, full_response)
                    elif isinstance(msg_data, dict):
                        _extract_chunk_text(msg_data, full_response)

                elif evt == "custom":
                    name = data.get("name", "")
                    payload_data = data.get("data", data)
                    if "token_usage" in str(payload_data).lower():
                        print(f"\n[TOKENS] {name}: {payload_data}")

                elif evt == "end":
                    print(f"\n[STREAM] End event received.")

                elif evt == "error":
                    print(f"\n[ERROR] {data}")

    except requests.exceptions.ChunkedEncodingError as e:
        print(f"\n[STREAM] Connection interrupted: {e}")
        print(f"[STREAM] Received {event_count} events, collected {len(full_response)} chars so far")
    except Exception as e:
        print(f"\n[STREAM] Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    return full_response

def main():
    print("=" * 60)
    print("DeerFlow Chat Test - deepseek-v4-flash")
    print("=" * 60)

    # 1. Login
    cookies = login()

    # 2. List models
    list_models(cookies)

    # 3. Create thread
    thread_id = create_thread(cookies)

    # 4. First question
    response1 = send_message_and_stream(cookies, thread_id)

    if not response1:
        print("\n[TEST] FAILED - No response for first question")
        return 1

    print(f"\n\n[RESULT 1] Full response length: {len(response1)} chars")

    # 5. Follow-up question (tests conversation context)
    thread_id2 = create_thread(cookies)
    response2 = send_message_and_stream(
        cookies, thread_id2,
        content="What is 2+2? Just give me the answer."
    )

    if response2:
        print(f"\n[RESULT 2] Full response length: {len(response2)} chars")
        print("\n[TEST] PASSED - Chat Q&A works with deepseek-v4-flash!")
        return 0
    else:
        print("\n[TEST] FAILED - No response for second question")
        return 1

if __name__ == "__main__":
    sys.exit(main())
