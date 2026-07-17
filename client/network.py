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

    # ── connect / disconnect ──────────────────

    def connect(self, ip, port, player_id, name, color_idx=0):
        self.server_addr = (ip, int(port))
        self.player_id = player_id
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)
        self.running = True

        threading.Thread(target=self._recv_loop, daemon=True).start()
        threading.Thread(target=self._ping_loop, daemon=True).start()

        # send join a few times (UDP is unreliable)
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
        try:
            data = json.dumps(payload).encode("utf-8")
            self.sock.sendto(data, self.server_addr)
        except Exception:
            pass

    # ── background threads ────────────────────

    def _recv_loop(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(16384)
                msg = json.loads(data.decode("utf-8"))
                self._on_message(msg)
            except socket.timeout:
                continue
            except OSError:
                if not self.running:
                    break
            except Exception:
                time.sleep(0.05)

    def _on_message(self, msg):
        mtype = msg.get("type")
        if mtype == "joined":
            if msg.get("player_id") == self.player_id:
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
        while self.running:
            if self.joined:
                self._ping_seq += 1
                self._pings[self._ping_seq] = time.time()
                self.send({"type": "ping", "player_id": self.player_id,
                           "seq": self._ping_seq})
                # purge very old ping entries
                cutoff = time.time() - 5
                self._pings = {k: v for k, v in self._pings.items() if v > cutoff}
            time.sleep(1.0)

    # ── convenience ───────────────────────────

    def get_latest_state(self):
        """Drain the queue and return only the most recent state (or None)."""
        latest = None
        while not self.state_queue.empty():
            try:
                latest = self.state_queue.get_nowait()
            except Empty:
                break
        return latest
