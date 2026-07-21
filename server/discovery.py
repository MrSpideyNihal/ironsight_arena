# server/discovery.py
# ──────────────────────────────────────────────
# UDP broadcast sender – fires once per second
# so LAN clients can auto-discover the host.
# ──────────────────────────────────────────────
import socket
import time
import json
import threading
from config.settings import DISCOVERY_PORT


def _get_local_ip():
    """Best-effort local-IP detection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_all_local_ips():
    ips = []
    try:
        # Standard connect method (usually gets the default gateway interface IP)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        if primary and primary != "127.0.0.1":
            ips.append(primary)
    except Exception:
        pass

    try:
        # Also grab other interfaces
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip != "127.0.0.1" and ip not in ips:
                # Prioritize 192.168.x.x and 10.x.x.x
                if ip.startswith("192.168.") or ip.startswith("10."):
                    ips.insert(0, ip)
                else:
                    ips.append(ip)
    except Exception:
        pass

    if not ips:
        ips.append("127.0.0.1")
    return ips


class DiscoveryBroadcaster(threading.Thread):
    def __init__(self, host_name, game_port):
        super().__init__(daemon=True)
        self.host_name = host_name
        self.game_port = game_port
        self.running = True

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)

        while self.running:
            local_ips = get_all_local_ips()
            for local_ip in local_ips:
                try:
                    payload = json.dumps({
                        "type": "discover",
                        "host_name": self.host_name,
                        "ip": local_ip,
                        "port": self.game_port,
                    }).encode("utf-8")

                    # Calculate subnet broadcast address
                    subnet_broadcast = "<broadcast>"
                    parts = local_ip.split('.')
                    if len(parts) == 4 and parts[0] != '127':
                        subnet_broadcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"

                    sock.sendto(payload, ("<broadcast>", DISCOVERY_PORT))
                    if subnet_broadcast != "<broadcast>":
                        sock.sendto(payload, (subnet_broadcast, DISCOVERY_PORT))
                except Exception:
                    pass
            time.sleep(1.0)

        sock.close()

    def stop(self):
        self.running = False
