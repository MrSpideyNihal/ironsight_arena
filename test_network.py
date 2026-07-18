"""
test_network.py - UDP connectivity diagnostic tool
=====================================================
Run this on BOTH machines to test if UDP packets are flowing.

HOST MACHINE: python test_network.py host
GUEST MACHINE: python test_network.py guest 192.168.25.104
"""
import socket
import sys
import time
import threading

PORT = 9999  # fresh port, no existing firewall rules

def run_host():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(1.0)

    # print local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "unknown"

    print(f"[HOST] Listening on 0.0.0.0:{PORT}")
    print(f"[HOST] Your IP is: {local_ip}")
    print(f"[HOST] Tell the GUEST to run: python test_network.py guest {local_ip}")
    print("[HOST] Waiting for packets from guest...")

    received = 0
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            received += 1
            msg = data.decode()
            print(f"[HOST] Packet #{received} received from {addr}: {msg}")
            # send response back
            sock.sendto(f"pong:{received}".encode(), addr)
        except socket.timeout:
            pass
        except KeyboardInterrupt:
            break

def run_guest(host_ip):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)
    server = (host_ip, PORT)

    print(f"[GUEST] Sending UDP packets to {host_ip}:{PORT}")
    print("[GUEST] Watch for responses from host...")

    for i in range(10):
        msg = f"ping:{i+1}"
        sock.sendto(msg.encode(), server)
        print(f"[GUEST] Sent: {msg}")
        try:
            data, addr = sock.recvfrom(1024)
            print(f"[GUEST] *** SUCCESS *** Got response from {addr}: {data.decode()}")
        except socket.timeout:
            print(f"[GUEST] No response (timeout) - host did not receive packet #{i+1}")
        time.sleep(0.5)

    sock.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  HOST:  python test_network.py host")
        print("  GUEST: python test_network.py guest <host_ip>")
        sys.exit(1)

    mode = sys.argv[1].lower()
    if mode == "host":
        run_host()
    elif mode == "guest":
        if len(sys.argv) < 3:
            print("Error: guest mode needs host IP")
            print("  Example: python test_network.py guest 192.168.25.104")
            sys.exit(1)
        run_guest(sys.argv[2])
    else:
        print(f"Unknown mode: {mode}. Use 'host' or 'guest'")
