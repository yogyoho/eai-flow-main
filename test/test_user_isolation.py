# -*- coding: utf-8 -*-
"""带认证的用户数据隔离功能测试脚本"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
import uuid

BASE_URL = "http://localhost:8001"

# 从 localStorage 获取测试 token (请替换为实际 token)
TEST_TOKEN = None  # 如果需要认证，设置此值

def get_headers():
    """获取请求头"""
    headers = {"Content-Type": "application/json"}
    if TEST_TOKEN:
        headers["Authorization"] = f"Bearer {TEST_TOKEN}"
    return headers


def test_memory_isolation():
    """测试记忆的用户隔离"""
    print("\n" + "="*60)
    print("Test 1: Memory User Isolation")
    print("="*60)
    
    user_a = f"user_{uuid.uuid4().hex[:8]}"
    user_b = f"user_{uuid.uuid4().hex[:8]}"
    
    # User A creates memory
    print(f"\n[1] User A ({user_a}) creates memory fact...")
    fact_data = {
        "content": "User A's private memory: This is private information",
        "category": "private",
        "confidence": 0.95
    }
    resp_a = requests.post(
        f"{BASE_URL}/api/memory/facts",
        json=fact_data,
        params={"user_id": user_a},
        headers=get_headers()
    )
    print(f"    Status: {resp_a.status_code}")
    if resp_a.status_code == 200:
        memory_a = resp_a.json()
        facts = memory_a.get('facts', [])
        print(f"    Memory fact count: {len(facts)}")
        if facts:
            print(f"    Memory content: {facts[0].get('content', 'N/A')}")
    
    # User B gets memory (should be empty or not see A's facts)
    print(f"\n[2] User B ({user_b}) gets memory...")
    resp_b = requests.get(
        f"{BASE_URL}/api/memory",
        params={"user_id": user_b},
        headers=get_headers()
    )
    print(f"    Status: {resp_b.status_code}")
    if resp_b.status_code == 200:
        memory_b = resp_b.json()
        facts_b = memory_b.get('facts', [])
        print(f"    Memory fact count: {len(facts_b)}")
        
        # Check if user A's content is visible to user B
        a_content_visible = any('User A' in str(f.get('content', '')) for f in facts_b)
        if len(facts_b) == 0 or not a_content_visible:
            print("    [OK] User B cannot see User A's memory - Isolation success!")
        else:
            print("    [FAIL] User B can see User A's memory - Isolation failed!")


def test_thread_isolation():
    """测试线程的用户隔离"""
    print("\n" + "="*60)
    print("Test 2: Thread User Isolation")
    print("="*60)
    
    user_x = f"user_{uuid.uuid4().hex[:8]}"
    user_y = f"user_{uuid.uuid4().hex[:8]}"
    
    # User X creates thread
    print(f"\n[1] User X ({user_x}) creates thread...")
    thread_data = {
        "user_id": user_x,  # 通过 body 传递 user_id
        "metadata": {"description": "User X's private thread"}
    }
    resp_x = requests.post(
        f"{BASE_URL}/api/threads",
        json=thread_data,
        headers=get_headers()
    )
    print(f"    Status: {resp_x.status_code}")
    thread_x_id = None
    if resp_x.status_code == 200:
        thread_x_id = resp_x.json().get("thread_id")
        print(f"    Thread ID: {thread_x_id}")
        print(f"    Thread metadata: {resp_x.json().get('metadata', {})}")
    
    # User Y searches threads
    print(f"\n[2] User Y ({user_y}) searches threads...")
    search_data = {"user_id": user_y}
    resp_y = requests.post(
        f"{BASE_URL}/api/threads/search",
        json=search_data,
        headers=get_headers()
    )
    print(f"    Status: {resp_y.status_code}")
    threads_y = []
    if resp_y.status_code == 200:
        threads_y = resp_y.json()
        print(f"    Thread count: {len(threads_y)}")
    
    # User X searches own threads
    print(f"\n[3] User X searches own threads...")
    search_x = {"user_id": user_x}
    resp_search = requests.post(
        f"{BASE_URL}/api/threads/search",
        json=search_x,
        headers=get_headers()
    )
    threads_x = []
    if resp_search.status_code == 200:
        threads_x = resp_search.json()
        print(f"    Thread count: {len(threads_x)}")
        if thread_x_id:
            found = any(t.get("thread_id") == thread_x_id for t in threads_x)
            if found:
                print("    [OK] User X can see own thread - success!")
    
    # Check isolation
    if thread_x_id:
        y_sees_x = any(t.get("thread_id") == thread_x_id for t in threads_y)
        if not y_sees_x and len(threads_x) > 0:
            print("    [OK] User Y cannot see User X's thread - Isolation success!")
        elif y_sees_x:
            print("    [FAIL] User Y can see User X's thread - Isolation failed!")


def test_agent_isolation():
    """测试智能体的用户隔离"""
    print("\n" + "="*60)
    print("Test 3: Agent/Soul User Isolation")
    print("="*60)
    
    user_m = f"user_{uuid.uuid4().hex[:8]}"
    user_n = f"user_{uuid.uuid4().hex[:8]}"
    agent_name = f"test-{uuid.uuid4().hex[:6]}"
    
    # User M creates agent
    print(f"\n[1] User M ({user_m}) creates agent: {agent_name}")
    agent_data = {
        "name": agent_name,
        "description": "User M's private agent",
        "soul": "# Soul\nThis is a private agent's soul definition."
    }
    resp_m = requests.post(
        f"{BASE_URL}/api/agents",
        json=agent_data,
        params={"user_id": user_m},
        headers=get_headers()
    )
    print(f"    Status: {resp_m.status_code}")
    if resp_m.status_code == 201:
        print(f"    Agent created: {resp_m.json().get('name')}")
    
    # User N lists agents
    print(f"\n[2] User N ({user_n}) lists agents...")
    resp_n = requests.get(
        f"{BASE_URL}/api/agents",
        params={"user_id": user_n},
        headers=get_headers()
    )
    print(f"    Status: {resp_n.status_code}")
    agents_n = []
    if resp_n.status_code == 200:
        agents_n = resp_n.json().get("agents", [])
        print(f"    Agent count: {len(agents_n)}")
        found_agent = any(a.get("name") == agent_name for a in agents_n)
    
    # User M lists own agents
    print(f"\n[3] User M lists own agents...")
    resp_m_list = requests.get(
        f"{BASE_URL}/api/agents",
        params={"user_id": user_m},
        headers=get_headers()
    )
    agents_m = []
    if resp_m_list.status_code == 200:
        agents_m = resp_m_list.json().get("agents", [])
        print(f"    Agent count: {len(agents_m)}")
        found_m = any(a.get("name") == agent_name for a in agents_m)
        if found_m:
            print("    [OK] User M can see own agent - success!")
    
    # Check isolation
    found_agent = any(a.get("name") == agent_name for a in agents_n)
    if not found_agent and len(agents_m) > 0:
        print("    [OK] User N cannot see User M's agent - Isolation success!")
    elif found_agent:
        print("    [FAIL] Agent isolation verification failed!")


def test_api_responses():
    """测试 API 响应结构"""
    print("\n" + "="*60)
    print("Test 4: API Response Structure Check")
    print("="*60)
    
    # Test memory endpoint
    print("\n[1] Memory API (without auth)...")
    resp = requests.get(f"{BASE_URL}/api/memory")
    print(f"    Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"    Response keys: {list(resp.json().keys())}")
    
    # Test agents endpoint
    print("\n[2] Agents API (without auth)...")
    resp = requests.get(f"{BASE_URL}/api/agents")
    print(f"    Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"    Response keys: {list(resp.json().keys())}")
    
    # Test threads search endpoint
    print("\n[3] Threads Search API (without auth)...")
    resp = requests.post(f"{BASE_URL}/api/threads/search", json={})
    print(f"    Status: {resp.status_code}")


def main():
    print("="*60)
    print("User Data Isolation Feature Test")
    print("="*60)
    
    # Check service availability
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"\nGateway service status: {resp.status_code}")
    except Exception as e:
        print(f"\nWARNING: Cannot connect to Gateway: {e}")
        print("Please ensure backend is running (make gateway or make dev)")
        return
    
    # Run tests
    try:
        test_api_responses()
        test_memory_isolation()
        test_thread_isolation()
        test_agent_isolation()
        
        print("\n" + "="*60)
        print("All tests completed!")
        print("="*60)
        
    except Exception as e:
        print(f"\nERROR during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
