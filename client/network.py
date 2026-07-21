# client/network.py
# ──────────────────────────────────────────────
# Threaded UDP network manager for the client.
# Runs a recv loop + ping loop on daemon threads
# and exposes a thread-safe state queue.
# ──────────────────────────────────────────────
import socket
import json
import time
import threading
from queue import Queue, Empty


class NetworkManager:
    def __init__(self):
        self.sock = None
        self.server_addr = None
        self.player_id = None
        self.running = False
        self.joined = False

        self.state_queue = Queue(maxsize=5)   # keep only freshest states
        self.latency = 0
        self.speed_multiplier = 1.0
        self.ammo_multiplier = 1.0
        self.kills_to_win = 10

        self._ping_seq = 0
        self._pings = {}
        self._last_input_time = 0
        self._input_send_interval = 1.0 / 20.0
        self._join_retry_count = 0

    # ── connect / disconnect ──────────────────

    def connect(self, ip, port, player_id, name, color_idx=0):
        self.server_addr = (ip, int(port))
        self.player_id = player_id
        self._player_name = name
        self._color_idx = color_idx
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)
        
        # Disable Windows SIO_UDP_CONNRESET to ignore ICMP port unreachable errors
        import os
        if os.name == 'nt':
            try:
                self.sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except AttributeError:
                pass

        self.running = True

        threading.Thread(target=self._recv_loop, daemon=True).start()
        threading.Thread(target=self._ping_loop, daemon=True).start()

        # Initial aggressive join burst
        join_msg = {"type": "join", "player_id": player_id, "name": name, "color_idx": color_idx}
        for i in range(5):
            self.send(join_msg)
            time.sleep(0.08)

    def disconnect(self):
        if not self.running:
            return
        self.running = False
        self.send({"type": "leave", "player_id": self.player_id})
        time.sleep(0.05)
        try:
            self.sock.close()
        except Exception:
            pass
        self.joined = False

    # ── send helper ───────────────────────────

    def send(self, payload):
        if not self.sock or not self.server_addr:
            return
        mtype = payload.get("type", "")
        # Rate-limit position input packets to reduce bandwidth
        if mtype == "input":
            now = time.time()
            if now - self._last_input_time < self._input_send_interval:
                return
            self._last_input_time = now
        try:
            data = json.dumps(payload).encode("utf-8")
            self.sock.sendto(data, self.server_addr)
            # Log join or ability packets to avoid spamming positions
            if mtype in ("join", "ability", "shoot", "respawn"):
                print(f"[Client Network] Sent '{mtype}' to {self.server_addr}", flush=True)
        except Exception as e:
            print(f"[Client Network Error] sendto failed to {self.server_addr}: {e}", flush=True)

    # ── background threads ────────────────────

    def _recv_loop(self):
        print(f"[Client Network] Receive thread started, listening for server packets...", flush=True)
        while self.running:
            try:
                data, addr = self.sock.recvfrom(16384)
                msg = json.loads(data.decode("utf-8"))
                mtype = msg.get("type")
                if mtype in ("joined", "pong"):
                    print(f"[Client Network] Received '{mtype}' from {addr}", flush=True)
                self._on_message(msg)
            except socket.timeout:
                continue
            except OSError as e:
                if not self.running:
                    break
                print(f"[Client Network Warning] Socket error: {e}", flush=True)
            except Exception as e:
                print(f"[Client Network Error] Decode failed: {e}", flush=True)
                time.sleep(0.05)

    def _on_message(self, msg):
        mtype = msg.get("type")
        if mtype == "joined":
            if msg.get("player_id") == self.player_id:
                if not self.joined:
                    print(f"[Client Network] Joined server successfully! Player ID: {self.player_id}", flush=True)
                self.joined = True
                self.speed_multiplier = msg.get("speed_mult", 1.0)
                self.ammo_multiplier = msg.get("ammo_mult", 1.0)
                self.kills_to_win = msg.get("kills_to_win", 10)
        elif mtype == "state":
            # Drop old states if queue is full
            if self.state_queue.full():
                try:
                    self.state_queue.get_nowait()
                except Empty:
                    pass
            self.state_queue.put(msg)
        elif mtype == "pong":
            seq = msg.get("seq")
            if seq in self._pings:
                self.latency = int((time.time() - self._pings.pop(seq)) * 1000)

    def _ping_loop(self):
        join_interval = 0.1
        while self.running:
            if self.joined:
                self._join_retry_count = 0
                join_interval = 0.1
                self._ping_seq += 1
                self._pings[self._ping_seq] = time.time()
                self.send({"type": "ping", "player_id": self.player_id,
                           "seq": self._ping_seq})
                # purge very old ping entries
                cutoff = time.time() - 5
                self._pings = {k: v for k, v in self._pings.items() if v > cutoff}
            else:
                # Retry join with increasing intervals
                name = getattr(self, '_player_name', 'Player')
                color_idx = getattr(self, '_color_idx', 0)
                self.send({
                    "type": "join",
                    "player_id": self.player_id,
                    "name": name,
                    "color_idx": color_idx
                })
                self._join_retry_count += 1
                join_interval = min(2.0, 0.1 * self._join_retry_count)
            time.sleep(join_interval)

    # ── convenience ───────────────────────────

    def pop_all_states(self):
        """Drain and return all state snapshots in the queue in order."""
        states = []
        while not self.state_queue.empty():
            try:
                states.append(self.state_queue.get_nowait())
            except Empty:
                break
        return states
