import socket
import sys

def check_port(host, port):
    print(f"Checking {host}:{port}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((host, port))
        print(f"✅ Port {port} is OPEN!")
        s.close()
        return True
    except Exception as e:
        print(f"❌ Port {port} is CLOSED or unreachable: {e}")
        return False

if __name__ == "__main__":
    check_port('127.0.0.1', 4001)
