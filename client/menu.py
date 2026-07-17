# client/menu.py
# ──────────────────────────────────────────────
# Main menu: Host / Join / Direct-connect,
# plus LAN auto-discovery listener.
# HIGH CONTRAST — works on any background color.
# ──────────────────────────────────────────────
import socket
import json
import time
import threading
from ursina import (Entity, Button, InputField, Text, color,
                    camera, destroy, window)
from config.settings import DISCOVERY_PORT, SERVER_PORT, PLAYER_COLORS, KILLS_TO_WIN_DEFAULT


class MainMenu(Entity):
    def __init__(self, on_host, on_join, **kwargs):
        super().__init__(parent=camera.ui, **kwargs)
        self.on_host_cb = on_host
        self.on_join_cb = on_join
        self._discovered = {}
        self._srv_btns = []
        self._alive = True

        self.selected_color_idx = 0
        self.speed_multiplier = 1.0
        self.ammo_multiplier = 1.0
        self.kills_to_win = KILLS_TO_WIN_DEFAULT

        # ── FULL SCREEN solid dark background ─
        #    (scale=10 guarantees it covers everything)
        self.bg = Entity(parent=self, model='quad', scale=10,
                         color=color.rgb32(15, 18, 25), z=1)

        # ── Title ─────────────────────────────
        Text(parent=self, text="IRONSIGHT  ARENA",
             origin=(0, 0), y=0.42, scale=3.2,
             color=color.rgb32(0, 200, 255))
        Text(parent=self, text="— LAN Arena Shooter —",
             origin=(0, 0), y=0.36, scale=1.6,
             color=color.rgb32(200, 200, 220))

        # Instructions / Help banner
        Text(parent=self, text="INSTRUCTIONS: Only 1 player clicks [HOST GAME]. The other player must join via the LAN list or type Host's IP (e.g. 192.168.25.251) in DIRECT IP and click CONNECT.",
             origin=(0, 0), y=0.31, scale=0.85,
             color=color.rgb32(255, 180, 50))

        # ── LEFT PANEL: Host / Connect ────────

        # nickname
        Text(parent=self, text="YOUR NAME:",
             origin=(-0.5, 0), position=(-0.55, 0.28), scale=1.4,
             color=color.white)
        self.name_field = InputField(parent=self, default_value="Player",
                                     scale=(0.35, 0.055),
                                     position=(-0.38, 0.22))

        # character color
        Text(parent=self, text="YOUR COLOR:",
             origin=(-0.5, 0), position=(-0.55, 0.14), scale=1.4,
             color=color.white)

        self._color_btns = []
        self._color_indicator_ent = None

        for idx, rgb in enumerate(PLAYER_COLORS):
            col_x = -0.52 + idx * 0.056
            btn = Button(
                parent=self,
                color=color.rgb32(*rgb),
                highlight_color=color.rgb32(min(255, rgb[0] + 30), min(255, rgb[1] + 30), min(255, rgb[2] + 30)),
                scale=(0.042, 0.042),
                position=(col_x, 0.08)
            )
            def make_color_cb(i=idx):
                return lambda: self._select_color(i)
            btn.on_click = make_color_cb()
            self._color_btns.append(btn)

        self._select_color(0)

        # server name
        Text(parent=self, text="SERVER NAME:",
             origin=(-0.5, 0), position=(-0.55, -0.01), scale=1.4,
             color=color.white)
        self.server_name_field = InputField(parent=self, default_value="My Arena Server",
                                            scale=(0.35, 0.055),
                                            position=(-0.38, -0.07))

        # speed toggle
        Text(parent=self, text="PLAYER SPEED:",
             origin=(-0.5, 0), position=(-0.55, -0.16), scale=1.4,
             color=color.white)
        self.speed_btn = Button(
            parent=self, text="1.0x",
            color=color.rgb32(40, 45, 55),
            highlight_color=color.rgb32(60, 65, 75),
            text_color=color.white,
            scale=(0.14, 0.045),
            position=(-0.28, -0.16)
        )
        self.speed_btn.on_click = self._toggle_speed

        # ammo toggle
        Text(parent=self, text="AMMO CAPACITY:",
             origin=(-0.5, 0), position=(-0.55, -0.23), scale=1.4,
             color=color.white)
        self.ammo_btn = Button(
            parent=self, text="1.0x",
            color=color.rgb32(40, 45, 55),
            highlight_color=color.rgb32(60, 65, 75),
            text_color=color.white,
            scale=(0.14, 0.045),
            position=(-0.28, -0.23)
        )
        self.ammo_btn.on_click = self._toggle_ammo

        # kills to win toggle
        Text(parent=self, text="KILLS TO WIN:",
             origin=(-0.5, 0), position=(-0.55, -0.30), scale=1.4,
             color=color.white)
        self.kills_btn = Button(
            parent=self, text=str(self.kills_to_win),
            color=color.rgb32(40, 45, 55),
            highlight_color=color.rgb32(60, 65, 75),
            text_color=color.white,
            scale=(0.14, 0.045),
            position=(-0.28, -0.30)
        )
        self.kills_btn.on_click = self._toggle_kills_to_win

        # host button
        self.host_btn = Button(
            parent=self, text="[ HOST GAME ]",
            color=color.rgb32(0, 120, 200),
            highlight_color=color.rgb32(0, 170, 255),
            text_color=color.white,
            scale=(0.35, 0.07),
            position=(-0.38, -0.39),
        )
        self.host_btn.on_click = self._click_host

        # direct IP
        Text(parent=self, text="DIRECT IP:",
             origin=(-0.5, 0), position=(-0.55, -0.40), scale=1.4,
             color=color.white)
        self.ip_field = InputField(parent=self, default_value="127.0.0.1",
                                   scale=(0.25, 0.055),
                                   position=(-0.42, -0.46))

        self.direct_btn = Button(
            parent=self, text="CONNECT",
            color=color.rgb32(200, 120, 0),
            highlight_color=color.rgb32(255, 160, 20),
            text_color=color.white,
            scale=(0.18, 0.06),
            position=(-0.20, -0.53),
        )
        self.direct_btn.on_click = self._click_direct

        # ── RIGHT PANEL: discovered servers ───
        Text(parent=self, text="SERVERS ON LAN:",
             origin=(0, 0), position=(0.30, 0.28), scale=1.6,
             color=color.rgb32(80, 255, 160))

        self._no_servers_text = Text(
            parent=self, text="Searching...",
            origin=(0, 0), position=(0.30, 0.18), scale=1.2,
            color=color.rgb32(140, 140, 140))

        # ── start discovery listener ──────────
        self._disc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._disc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._disc_sock.bind(("", DISCOVERY_PORT))
        except Exception as e:
            print(f"[Menu] Discovery bind failed: {e}")
        self._disc_sock.settimeout(0.5)
        threading.Thread(target=self._listen, daemon=True).start()

    # ── Ursina per-frame ──────────────────────

    def update(self):
        if not self._alive:
            return
        now = time.time()

        # purge stale
        self._discovered = {k: v for k, v in self._discovered.items()
                            if now - v["t"] < 5}

        # Check if the set of discovered servers has changed (IP, name, port)
        current_servers = {(ip, info["name"], info["port"]) for ip, info in self._discovered.items()}
        if not hasattr(self, '_last_servers') or self._last_servers != current_servers:
            self._last_servers = current_servers
            self._rebuild_server_buttons()

    def _rebuild_server_buttons(self):
        for b in self._srv_btns:
            destroy(b)
        self._srv_btns.clear()

        if self._discovered:
            self._no_servers_text.text = ""
        else:
            self._no_servers_text.text = "Searching..."

        def create_click_handler(srv_ip, srv_port):
            return lambda: self._click_discovered(srv_ip, srv_port)

        for i, (ip, info) in enumerate(self._discovered.items()):
            label = f"{info['name']}  ({ip})"
            btn = Button(
                parent=self, text=label,
                color=color.rgb32(0, 160, 80),
                highlight_color=color.rgb32(0, 210, 110),
                text_color=color.white,
                scale=(0.45, 0.06),
                position=(0.30, 0.16 - i * 0.08),
            )
            btn.on_click = create_click_handler(ip, info['port'])
            self._srv_btns.append(btn)

    # ── discovery listener thread ─────────────

    def _listen(self):
        while self._alive:
            try:
                data, addr = self._disc_sock.recvfrom(2048)
                msg = json.loads(data.decode("utf-8"))
                if msg.get("type") == "discover":
                    sender_ip = addr[0]
                    self._discovered[sender_ip] = {
                        "name": msg["host_name"],
                        "port": msg["port"],
                        "t": time.time(),
                    }
            except socket.timeout:
                continue
            except Exception:
                break

    # ── click handlers ────────────────────────

    def _select_color(self, idx):
        self.selected_color_idx = idx
        if not hasattr(self, '_color_btns') or not self._color_btns:
            return
        if self._color_indicator_ent:
            destroy(self._color_indicator_ent)
        selected_btn = self._color_btns[idx]
        self._color_indicator_ent = Entity(
            parent=self,
            model='quad',
            color=color.white,
            scale=(0.052, 0.052),
            position=(selected_btn.x, selected_btn.y, selected_btn.z + 0.01)
        )

    def _toggle_speed(self):
        speeds = [1.0, 1.2, 1.5, 2.0]
        curr_idx = speeds.index(self.speed_multiplier)
        self.speed_multiplier = speeds[(curr_idx + 1) % len(speeds)]
        self.speed_btn.text = f"{self.speed_multiplier}x"

    def _toggle_ammo(self):
        ammos = [1.0, 1.5, 2.0, 999.0]
        curr_idx = ammos.index(self.ammo_multiplier)
        self.ammo_multiplier = ammos[(curr_idx + 1) % len(ammos)]
        if self.ammo_multiplier == 999.0:
            self.ammo_btn.text = "INFINITE"
        else:
            self.ammo_btn.text = f"{self.ammo_multiplier}x"

    def _toggle_kills_to_win(self):
        values = [5, 10, 15, 20]
        curr_idx = values.index(self.kills_to_win)
        self.kills_to_win = values[(curr_idx + 1) % len(values)]
        self.kills_btn.text = str(self.kills_to_win)

    def _click_host(self):
        name = self.name_field.text or "Player"
        server_name = self.server_name_field.text or f"{name}'s Server"
        self._shutdown()
        self.on_host_cb(name, server_name, self.speed_multiplier, self.ammo_multiplier, self.selected_color_idx, self.kills_to_win)

    def _click_direct(self):
        name = self.name_field.text or "Player"
        ip = self.ip_field.text or "127.0.0.1"
        self._shutdown()
        self.on_join_cb(ip, name, SERVER_PORT, self.selected_color_idx)

    def _click_discovered(self, ip, port):
        name = self.name_field.text or "Player"
        self._shutdown()
        self.on_join_cb(ip, name, port, self.selected_color_idx)

    def _shutdown(self):
        self._alive = False
        if self._color_indicator_ent:
            destroy(self._color_indicator_ent)
        for b in self._color_btns:
            destroy(b)
        try:
            self._disc_sock.close()
        except Exception:
            pass
        destroy(self)
