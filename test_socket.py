import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(('127.0.0.1', 4001))
    s.sendall(b'GET /openapi.json HTTP/1.1\r\nHost: localhost\r\n\r\n')
    data = s.recv(8192).decode('utf-8', errors='replace')
    print(f"Response:\n{data[:500]}")
    # Check if it's the gateway
    if 'openapi' in data.lower() or 'paths' in data.lower():
        print("Server is responding with OpenAPI - Gateway is UP")
    else:
        print(f"Server response length: {len(data)}")
except Exception as e:
    print(f"Connection failed: {type(e).__name__}: {e}")
finally:
    s.close()
