# server/server.py
# ──────────────────────────────────────────────
# Authoritative UDP game server.
#   • recv thread  → parse client messages
#   • tick thread  → update state, broadcast
#   • discovery    → LAN broadcast thread
# ──────────────────────────────────────────────
import socket
import json
import time
import threading
from config.settings import SERVER_PORT, TICK_INTERVAL, WEAPON_DAMAGE, KILLS_TO_WIN_DEFAULT
from server.game_state import GameState
from server.discovery import DiscoveryBroadcaster, _get_local_ip


class ArenaServer:
    def __init__(self, host_name="Host Game", speed_mult=1.0, ammo_mult=1.0, kills_to_win=KILLS_TO_WIN_DEFAULT):
        self.host_name = host_name
        self.port = SERVER_PORT
        self.state = GameState()
        self.speed_mult = speed_mult
        self.ammo_mult = ammo_mult
        self.kills_to_win = kills_to_win
        self.state.set_kills_to_win(kills_to_win)

        self.clients_lock = threading.Lock()
        self.clients = {}  # (ip, port) → {"id": str, "last_seen": float}
        self._input_throttle = {}  # pid → last_input_time
        self._input_throttle_interval = 1.0 / 30.0  # Max 30 input updates/sec per client

        self.running = False
        self.sock = None
        self.discovery = None

    # ── lifecycle ──────────────────────────────

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Disable Windows SIO_UDP_CONNRESET to ignore ICMP port unreachable errors
        import os
        if os.name == 'nt':
            try:
                self.sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except AttributeError:
                pass

        # Try to bind to self.port, fallback to other ports if already in use
        bound = False
        for offset in range(10):
            try:
                target_port = self.port + offset
                self.sock.bind(("0.0.0.0", target_port))
                self.port = target_port
                bound = True
                break
            except OSError:
                continue

        if not bound:
            print(f"[Server] Failed to bind to any port starting from {self.port}!", flush=True)
            return

        self.sock.settimeout(1.0)

        host_ip = _get_local_ip()
        print(f"[Server] ╔══════════════════════════════════════╗", flush=True)
        print(f"[Server] ║  IRONSIGHT ARENA SERVER RUNNING     ║", flush=True)
        print(f"[Server] ║  IP: {host_ip:<15}         ║", flush=True)
        print(f"[Server] ║  Port: {self.port:<5}                   ║", flush=True)
        print(f"[Server] ║  Tell guests to connect via:        ║", flush=True)
        print(f"[Server] ║  {host_ip}:{self.port:<5}                  ║", flush=True)
        print(f"[Server] ╚══════════════════════════════════════╝", flush=True)

        self.running = True

        threading.Thread(target=self._recv_loop,  daemon=True).start()
        threading.Thread(target=self._tick_loop,  daemon=True).start()

        self.discovery = DiscoveryBroadcaster(self.host_name, self.port)
        self.discovery.start()

    def stop(self):
        self.running = False
        if self.discovery:
            self.discovery.stop()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        print("[Server] Stopped.")

    # ── receive loop ───────────────────────────

    def _recv_loop(self):
        print("[Server] Receive loop started. Waiting for UDP packets...", flush=True)
        while self.running:
            try:
                data, addr = self.sock.recvfrom(8192)
                msg = json.loads(data.decode("utf-8"))
                mtype = msg.get("type")
                # Log joins and actions to avoid position tick spam
                if mtype in ("join", "ability", "shoot", "respawn", "leave"):
                    print(f"[Server Network] Received '{mtype}' from {addr} (player_id={msg.get('player_id')})", flush=True)
                self._handle(msg, addr)
            except socket.timeout:
                continue
            except OSError as exc:
                if not self.running:
                    break
                print(f"[Server Network Warning] Socket error: {exc}", flush=True)
            except Exception as exc:
                print(f"[Server Network Error] Decode failed: {exc}", flush=True)

    def _handle(self, msg, addr):
        mtype = msg.get("type")
        pid   = msg.get("player_id")

        # Dynamically update client port/address mapping if the player_id is provided
        if pid:
            with self.clients_lock:
                if addr not in self.clients or self.clients[addr]["id"] != pid:
                    # Remove stale port mappings for this pid
                    stale = [a for a, info in self.clients.items() if info["id"] == pid]
                    for a in stale:
                        if a != addr:
                            del self.clients[a]
                    self.clients[addr] = {"id": pid, "last_seen": time.time()}
                    # If player not in state yet, let join packet handle creation

        if mtype == "join":
            name = msg.get("name", "Player")
            color_idx = msg.get("color_idx", 0)
            with self.clients_lock:
                # Remove stale address mapping for the same player_id (rejoin support)
                stale_addrs = [a for a, info in self.clients.items() if info["id"] == pid]
                for a in stale_addrs:
                    if a != addr:
                        del self.clients[a]

                self.clients[addr] = {"id": pid, "last_seen": time.time()}
                created = self.state.add_player(pid, name, color_idx)
                if created:
                    print(f"[Server] + {name} ({pid}) from {addr}", flush=True)

            resp = json.dumps({
                "type": "joined",
                "player_id": pid,
                "speed_mult": self.speed_mult,
                "ammo_mult": self.ammo_mult,
                "kills_to_win": self.kills_to_win,
            }).encode("utf-8")
            self.sock.sendto(resp, addr)

        elif mtype == "input":
            mapped_pid = None
            with self.clients_lock:
                if addr in self.clients:
                    mapped_pid = self.clients[addr]["id"]
                    self.clients[addr]["last_seen"] = time.time()
            if not mapped_pid or (pid and pid != mapped_pid):
                return
            # Server-side input rate limiting
            now = time.time()
            last = self._input_throttle.get(mapped_pid, 0)
            if now - last < self._input_throttle_interval:
                return
            self._input_throttle[mapped_pid] = now
            self.state.update_player_input(mapped_pid, msg.get("pos", [0, 0, 0]), msg.get("rot", 0), msg.get("weapon", "Assault Rifle"))

        elif mtype == "shoot":
            mapped_pid = None
            with self.clients_lock:
                if addr in self.clients:
                    mapped_pid = self.clients[addr]["id"]
                    self.clients[addr]["last_seen"] = time.time()
            if not mapped_pid or (pid and pid != mapped_pid):
                return
            self.state.handle_shoot(mapped_pid, msg.get("target_id"), msg.get("damage", WEAPON_DAMAGE))

        elif mtype == "respawn":
            mapped_pid = None
            with self.clients_lock:
                if addr in self.clients:
                    mapped_pid = self.clients[addr]["id"]
                    self.clients[addr]["last_seen"] = time.time()
            print(f"[Server] Received manual respawn request for mapped_pid={mapped_pid}, pid={pid}", flush=True)
            if not mapped_pid or (pid and pid != mapped_pid):
                return
            success = self.state.force_respawn(mapped_pid)
            print(f"[Server] force_respawn status: {success}", flush=True)

        elif mtype == "ability":
            mapped_pid = None
            with self.clients_lock:
                if addr in self.clients:
                    mapped_pid = self.clients[addr]["id"]
                    self.clients[addr]["last_seen"] = time.time()
            if not mapped_pid or (pid and pid != mapped_pid):
                return

            ability = msg.get("ability")
            if ability == "grenade":
                self.state.spawn_grenade(
                    mapped_pid,
                    msg.get("pos", [0, 0, 0]),
                    msg.get("rot", 0.0),
                    msg.get("forward", [0, 0, 1]),
                    msg.get("up", 0.0),
                )
            elif ability == "pickup_touch":
                self.state.apply_pickup_touch(mapped_pid, msg.get("pos", [0, 0, 0]))

        elif mtype == "ping":
            with self.clients_lock:
                if addr in self.clients:
                    self.clients[addr]["last_seen"] = time.time()
            resp = json.dumps({"type": "pong", "seq": msg.get("seq")}).encode("utf-8")
            self.sock.sendto(resp, addr)

        elif mtype == "leave":
            mapped_pid = None
            with self.clients_lock:
                if addr in self.clients:
                    mapped_pid = self.clients[addr]["id"]
                    print(f"[Server] - {pid} left.")
                    self.state.remove_player(mapped_pid)
                    del self.clients[addr]

    # ── tick loop ──────────────────────────────

    def _tick_loop(self):
        tick = 0
        while self.running:
            t0 = time.time()

            self.state.update()  # respawn timers etc.

            # — timeout stale clients ——————————
            now = time.time()
            stale = []
            with self.clients_lock:
                for addr, info in self.clients.items():
                    if now - info["last_seen"] > 3.0:
                        stale.append(addr)

            for addr in stale:
                with self.clients_lock:
                    if addr in self.clients:
                        pid = self.clients[addr]["id"]
                        print(f"[Server] x {pid} timed out")
                        self.state.remove_player(pid)
                        del self.clients[addr]

            # — broadcast state ————————————————
            snap = self.state.snapshot()
            events       = self.state.pop_events()
            payload = json.dumps({
                "type": "state",
                "tick": tick,
                "players": snap["players"],
                "pickups": snap["pickups"],
                "grenades": snap["grenades"],
                "match_over": snap["match_over"],
                "winner_id": snap["winner_id"],
                "winner_name": snap["winner_name"],
                "kills_to_win": snap["kills_to_win"],
                "events": events,
            }).encode("utf-8")

            with self.clients_lock:
                addrs = list(self.clients.keys())

            for addr in addrs:
                try:
                    self.sock.sendto(payload, addr)
                except Exception:
                    pass

            tick += 1
            elapsed = time.time() - t0
            time.sleep(max(0.001, TICK_INTERVAL - elapsed))


# Allow running the server standalone for debugging
if __name__ == "__main__":
    srv = ArenaServer()
    srv.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
