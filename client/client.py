# client/client.py
# ──────────────────────────────────────────────
# Main client: wires together the Ursina world,
# network manager, HUD, players, and camera.
# ──────────────────────────────────────────────
import uuid
import time
from ursina import (Entity, mouse, camera, color, Vec3, destroy,
                    window, time as ursina_time, curve)
from config.settings import SERVER_PORT, PLAYER_MAX_HP, RESPAWN_TIME
from client.network import NetworkManager
from client.camera_controller import ThirdPersonCamera
from client.player import LocalPlayer, RemotePlayer
from client.hud import GameHUD
from client.menu import MainMenu
from maps.arena_01 import build_arena


class HealthPickupVisual(Entity):
    def __init__(self, position, **kwargs):
        super().__init__(
            position=position,
            scale=1.0,
            **kwargs
        )
        # Bobbing first-aid box
        self.box = Entity(
            parent=self,
            model='cube',
            color=color.rgb32(220, 40, 40),
            scale=(0.65, 0.45, 0.28)
        )
        # White cross horizontal bar
        self.cross_h = Entity(
            parent=self.box,
            model='cube',
            color=color.white,
            scale=(0.35, 0.12, 1.05),
            position=(0, 0, 0)
        )
        # White cross vertical bar
        self.cross_v = Entity(
            parent=self.box,
            model='cube',
            color=color.white,
            scale=(0.12, 0.35, 1.05),
            position=(0, 0, 0)
        )

    def update(self):
        import math
        self.rotation_y += 120.0 * ursina_time.dt
        self.y = self.y + math.sin(ursina_time.time() * 4.0) * 0.005


class GameClient:
    def __init__(self):
        self.network = NetworkManager()
        self.player_id = f"p_{uuid.uuid4().hex[:8]}"
        self.player_name = "Player"
        self.selected_color_idx = 0

        self.local_player = None
        self.remote_players = {}
        self.cam_ctrl = None
        self.hud = None
        self.arena_ents = []
        self.started = False

        # State interpolation buffer for smooth remote player movement
        self._state_buffer = []  # [(receive_time, state), ...]
        self._interp_delay = 0.05  # 50ms interpolation delay (optimal for LAN)
        self._last_state_time = time.time()

        # show main menu first
        self.menu = MainMenu(on_host=self.host_game, on_join=self.join_game)

    # ── menu callbacks ────────────────────────

    def host_game(self, nickname, port=SERVER_PORT):
        """Called by the menu (or main.py wrapper) after server thread starts."""
        self.player_name = nickname
        self._init_world()
        self.network.connect("127.0.0.1", port, self.player_id, nickname, getattr(self, "selected_color_idx", 0))

    def join_game(self, ip, nickname, port=SERVER_PORT, color_idx=0):
        self.player_name = nickname
        self.selected_color_idx = color_idx
        if ":" in ip:
            parts = ip.split(":")
            ip = parts[0]
            try:
                port = int(parts[1])
            except ValueError:
                pass
        self._init_world()
        self.network.connect(ip, port, self.player_id, nickname, color_idx)

    # ── world setup ───────────────────────────

    def _init_world(self):
        self.arena_ents = build_arena()

        mouse.locked = True
        mouse.visible = False

        # local player
        self.local_player = LocalPlayer(
            player_id=self.player_id,
            name=self.player_name,
            network=self.network,
            position=Vec3(0, 5, 8),
        )

        # camera
        self.cam_ctrl = ThirdPersonCamera(target=self.local_player)
        self.local_player.cam_ctrl = self.cam_ctrl

        # HUD
        self.hud = GameHUD()
        self.local_player.hud = self.hud

        self.started = True

    # ── per-frame (called from main.py) ───────

    def update(self):
        if not self.started:
            return

        dt = ursina_time.dt
        self.hud.update_tick(dt)
        self.hud.set_ping(self.network.latency)

        if self.local_player:
            self.hud.update_cooldowns(self.local_player._dash_cooldown, self.local_player._grenade_cooldown)

        # Apply server speed and ammo settings once connected
        if self.network.joined and not getattr(self, '_applied_host_settings', False):
            self._applied_host_settings = True
            self.local_player.speed_multiplier = self.network.speed_multiplier
            self.local_player.weapon.ammo_multiplier = self.network.ammo_multiplier
            self.local_player.weapon.switch_to(self.local_player.weapon.weapon_name, force=True)
            ktw = getattr(self.network, 'kills_to_win', 10)
            if hasattr(self.hud, 'show_kills_to_win'):
                self.hud.show_kills_to_win(ktw)
            else:
                self.hud.set_status(f"KILLS TO WIN: {ktw}")

        # if dead, update respawn countdown status message
        if self.local_player and not self.local_player.alive:
            elapsed = time.time() - getattr(self, '_death_time', time.time())
            remaining = max(0.0, RESPAWN_TIME - elapsed)
            if remaining > 0:
                self.hud.set_status(f"YOU DIED - PRESS K TO RESPAWN ({remaining:.1f}s)")
            else:
                self.hud.set_status("YOU DIED - PRESS K TO RESPAWN")

            # Check K key to respawn robustly
            from ursina import held_keys as urs_held_keys
            if urs_held_keys['k'] and self.network and self.network.joined:
                if not getattr(self, '_k_respawn_down', False):
                    self._k_respawn_down = True
                    print("[Client] K key pressed! Sending manual respawn request...", flush=True)
                    self.network.send({
                        "type": "respawn",
                        "player_id": self.player_id,
                    })
            else:
                self._k_respawn_down = False

        # drain network states into interpolation buffer
        states = self.network.pop_all_states()
        now = time.time()
        if states:
            self._last_state_time = now
            for s in states:
                self._state_buffer.append((now, s))

        if self.network.joined:
            if now - getattr(self, '_last_state_time', now) > 2.0:
                print(f"[Client] Connection timed out (no states for 2.0s). Rejoining...", flush=True)
                self.network.joined = False
                self._applied_host_settings = False
                self._last_state_time = now

        if self._state_buffer:
            # Keep only last 1 second of states
            cutoff = now - 1.0
            self._state_buffer = [(t, s) for t, s in self._state_buffer if t > cutoff]

        # Apply interpolated state for smooth remote player rendering
        interp_state = self._build_interpolated_state()
        if interp_state:
            self._apply_state(interp_state, dt)

    def _build_interpolated_state(self):
        if not self._state_buffer:
            return None
        if len(self._state_buffer) < 2:
            return self._state_buffer[-1][1]

        now = time.time()
        render_time = now - self._interp_delay

        past = None
        future = None
        for i in range(len(self._state_buffer) - 1):
            t1, s1 = self._state_buffer[i]
            t2, s2 = self._state_buffer[i + 1]
            if t1 <= render_time <= t2:
                past = (t1, s1)
                future = (t2, s2)
                break

        if not past or not future:
            past = self._state_buffer[-2]
            future = self._state_buffer[-1]

        t_diff = future[0] - past[0]
        if t_diff <= 0:
            return future[1]

        t = (render_time - past[0]) / t_diff
        t = max(0.0, min(1.0, t))

        import copy
        result = copy.deepcopy(future[1])

        past_players = past[1].get("players", {})
        future_players = result.get("players", {})

        for pid, f_data in future_players.items():
            if pid == self.player_id:
                continue
            p_data = past_players.get(pid)
            if p_data:
                px = p_data["pos"][0] + (f_data["pos"][0] - p_data["pos"][0]) * t
                py = p_data["pos"][1] + (f_data["pos"][1] - p_data["pos"][1]) * t
                pz = p_data["pos"][2] + (f_data["pos"][2] - p_data["pos"][2]) * t
                f_data["pos"] = [px, py, pz]
                f_data["rot"] = p_data["rot"] + (f_data["rot"] - p_data["rot"]) * t

        # Merge all events from buffered states to prevent dropping feed events
        all_events = []
        for _, s in self._state_buffer:
            all_events.extend(s.get("events", []))
        result["events"] = all_events

        return result

    def _apply_state(self, state, dt):
        players = state.get("players", {})
        events  = state.get("events", [])

        # scoreboard
        self.hud.draw_scoreboard(players)

        # ── local player HP / alive ───────────
        me = players.get(self.player_id)
        if me:
            old_hp = getattr(self.local_player, 'hp', PLAYER_MAX_HP)
            self.local_player.hp = me["hp"]
            self.hud.set_hp(me["hp"])
            if me["hp"] < old_hp:
                self.hud.flash_damage()
            self.hud.set_kd(me.get("kills", 0), me.get("deaths", 0))
            self.local_player.set_color_from_idx(me.get("color_idx", 0))
            if me["alive"] and not self.local_player.alive:
                self.local_player.respawn_at(me["pos"])
                self.hud.set_status("")
            elif not me["alive"] and self.local_player.alive:
                self.local_player.die()
                self._death_time = time.time()
                self.hud.set_status("YOU DIED - PRESS K TO RESPAWN")
                self.hud.flash_damage()
        else:
            # If we are not in the server's players list, we have been timed out or disconnected.
            # Reset joined status to trigger a rejoin handshake.
            if self.network.joined:
                print(f"[Client] Not found in server player list. Rejoining...", flush=True)
                self.network.joined = False
                self._applied_host_settings = False

        # ── remote players ────────────────────
        for pid, data in players.items():
            if pid == self.player_id:
                continue

            if pid not in self.remote_players:
                self.remote_players[pid] = RemotePlayer(pid, data.get("name", "?"))

            rp = self.remote_players[pid]
            rp.target_pos = Vec3(*data["pos"])
            rp.target_rot = data["rot"]
            rp.set_hp_visual(data.get("hp", PLAYER_MAX_HP))
            rp.set_color_from_idx(data.get("color_idx", 0))
            if hasattr(rp, 'update_weapon_visual'):
                rp.update_weapon_visual(data.get("weapon", "Assault Rifle"))

            if data["alive"] and not rp.alive:
                rp.respawn_at(data["pos"])
            elif not data["alive"] and rp.alive:
                rp.die()

        # remove disconnected remotes
        gone = [pid for pid in self.remote_players if pid not in players]
        for pid in gone:
            self.remote_players[pid].cleanup()
            del self.remote_players[pid]

        # match over countdown
        if state.get("match_over"):
            winner_name = state.get("winner_name", "Someone")
            restart_in = state.get("restart_in", 10.0)
            self.hud.set_status(f"{winner_name.upper()} WINS!\nRestarting in {restart_in:.1f}s")

        # ── events ────────────────────────────
        for ev in events:
            t = ev.get("type")
            if t == "join":
                self.hud.add_feed(f"+ {ev['name']} joined")
            elif t == "leave":
                self.hud.add_feed(f"- {ev['name']} left")
            elif t == "kill":
                self.hud.add_feed(
                    f"{ev['shooter_name']}  >>  {ev['target_name']}")
                # show elimination banner if WE got the kill
                if ev.get('shooter_id') == self.player_id:
                    self.hud.show_elimination(ev.get('target_name', '?'))
            elif t == "spawn":
                if ev["player_id"] == self.player_id:
                    self.local_player.respawn_at(ev["pos"])
                    self.hud.set_status("")
            elif t == "pickup_spawn":
                pass
            elif t == "pickup_taken":
                if ev.get("player_id") == self.player_id:
                    self.hud.add_feed(f"+ HP {ev.get('hp', 0)}")
            elif t == "grenade_explode":
                self.hud.add_feed("* grenade exploded")
                try:
                    import random
                    import math as pymath
                    from config.settings import GRENADE_RADIUS
                    
                    pos = Vec3(*ev.get("pos", [0, 0, 0]))
                    
                    # Expanding blast sphere
                    blast = Entity(
                        model='sphere',
                        color=color.rgba32(255, 120, 20, 240),
                        position=pos,
                        scale=0.2
                    )
                    blast.animate_scale(GRENADE_RADIUS * 1.5, duration=0.35, curve=curve.out_quad)
                    blast.animate_color(color.rgba32(255, 40, 0, 0), duration=0.35, curve=curve.out_quad)
                    destroy(blast, delay=0.36)
                    
                    # Outward spark particles
                    for i in range(12):
                        angle = (i / 12) * pymath.pi * 2
                        dir_vec = Vec3(pymath.sin(angle), random.uniform(-0.2, 0.5), pymath.cos(angle)).normalized()
                        spark = Entity(
                            model='cube',
                            color=color.rgb32(255, 200, 50),
                            position=pos,
                            scale=0.15
                        )
                        spark.animate_position(pos + dir_vec * random.uniform(3.0, 6.0), duration=0.45, curve=curve.out_quad)
                        spark.animate_scale(0.01, duration=0.45)
                        destroy(spark, delay=0.46)
                except Exception as e:
                    print(f"Failed to spawn grenade blast visual: {e}")
            elif t == "match_end":
                pass  # Handled dynamically by state.get("match_over")
            elif t == "match_start":
                self.hud.set_status("")
                self.hud.add_feed("Match Started / Restarted!")

        pickups = state.get("pickups", [])
        grenades = state.get("grenades", [])

        # Only check pickup touches if local player is alive and NOT at max HP
        if self.local_player and self.local_player.alive and self.network and self.network.joined and self.local_player.hp < PLAYER_MAX_HP:
            if not hasattr(self, '_pickup_touch_cooldown'):
                self._pickup_touch_cooldown = 0.0
            self._pickup_touch_cooldown = max(0.0, self._pickup_touch_cooldown - dt)
            
            if self._pickup_touch_cooldown <= 0:
                for pickup in pickups:
                    dx = pickup["pos"][0] - self.local_player.x
                    dy = pickup["pos"][1] - self.local_player.y
                    dz = pickup["pos"][2] - self.local_player.z
                    if (dx * dx + dy * dy + dz * dz) ** 0.5 <= pickup.get("radius", 2.0):
                        self.network.send({
                            "type": "ability",
                            "ability": "pickup_touch",
                            "player_id": self.player_id,
                            "pos": [self.local_player.x, self.local_player.y, self.local_player.z],
                        })
                        self._pickup_touch_cooldown = 0.1
                        break

        if not hasattr(self, '_pickup_ents'):
            self._pickup_ents = {}
        if not hasattr(self, '_grenade_ents'):
            self._grenade_ents = {}

        active_pickups = set()
        for pickup in pickups:
            pid = pickup["id"]
            active_pickups.add(pid)
            if pid not in self._pickup_ents:
                self._pickup_ents[pid] = HealthPickupVisual(position=Vec3(*pickup["pos"]))
            ent = self._pickup_ents[pid]
            # Update position (just in case)
            ent.position = Vec3(*pickup["pos"])
        for pid in list(self._pickup_ents.keys()):
            if pid not in active_pickups:
                destroy(self._pickup_ents[pid])
                del self._pickup_ents[pid]

        active_grenades = set()
        for grenade in grenades:
            gid = grenade["id"]
            active_grenades.add(gid)
            if gid not in self._grenade_ents:
                self._grenade_ents[gid] = Entity(model='sphere', color=color.rgb32(255, 170, 40), scale=0.35)
            self._grenade_ents[gid].position = Vec3(*grenade["pos"])
        for gid in list(self._grenade_ents.keys()):
            if gid not in active_grenades:
                destroy(self._grenade_ents[gid])
                del self._grenade_ents[gid]

    # ── cleanup ───────────────────────────────

    def shutdown(self):
        self.network.disconnect()
        if self.local_player:
            self.local_player.cleanup()
        for rp in self.remote_players.values():
            rp.cleanup()
        self.remote_players.clear()
        if self.hud:
            self.hud.destroy_all()
