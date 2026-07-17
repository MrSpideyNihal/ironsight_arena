# server/game_state.py
# ──────────────────────────────────────────────
# Authoritative game-state tracker.  Thread-safe
# via a lock so the tick thread and recv thread
# never corrupt the player dict.
# ──────────────────────────────────────────────
import random
import time
import threading
from config.settings import (
    PLAYER_MAX_HP, SPAWN_POINTS, RESPAWN_TIME, WEAPON_DAMAGE,
    KILLS_TO_WIN_DEFAULT, HEAL_PICKUP_HEAL_AMOUNT, HEAL_PICKUP_LIFETIME,
    HEAL_PICKUP_RADIUS, GRENADE_FUSE, GRENADE_RADIUS, GRENADE_DAMAGE,
    STATIC_COLLIDERS
)


class GameState:
    def __init__(self):
        self.lock = threading.RLock()
        self.players = {}
        self.pickups = []
        self.grenades = []
        self.match_over = False
        self.winner_id = None
        self.winner_name = None
        self.kills_to_win = KILLS_TO_WIN_DEFAULT
        # player_id → {
        #   "pos": [x,y,z], "rot": yaw, "hp": int,
        #   "alive": bool, "name": str,
        #   "kills": int, "deaths": int,
        #   "respawn_at": float
        # }
        self.events = []

    # ── player management ─────────────────────

    def add_player(self, player_id, name="Player", color_idx=0):
        with self.lock:
            if player_id in self.players:
                # Duplicate join packets for an active player are a no-op.
                # The server can retry the join handshake without resetting the match state.
                self.players[player_id]["name"] = name
                self.players[player_id]["color_idx"] = color_idx
                return False
            else:
                spawn = list(random.choice(SPAWN_POINTS))
                self.players[player_id] = {
                    "pos": spawn,
                    "rot": 0.0,
                    "hp": PLAYER_MAX_HP,
                    "alive": True,
                    "name": name,
                    "kills": 0,
                    "deaths": 0,
                    "respawn_at": 0,
                    "color_idx": color_idx,
                    "weapon": "Assault Rifle",
                }
            self.events.append({"type": "join", "player_id": player_id, "name": name})
            return True

    def set_kills_to_win(self, kills_to_win):
        with self.lock:
            self.kills_to_win = max(1, int(kills_to_win))

    def spawn_heal_pickup(self, pos):
        with self.lock:
            self.pickups.append({
                "id": f"hp_{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
                "pos": list(pos),
                "heal": HEAL_PICKUP_HEAL_AMOUNT,
                "spawned_at": time.time(),
                "lifetime": HEAL_PICKUP_LIFETIME,
                "radius": HEAL_PICKUP_RADIUS,
            })

    def spawn_grenade(self, player_id, pos, rot, forward, up):
        with self.lock:
            player = self.players.get(player_id)
            if not player or not player["alive"]:
                return False
            self.grenades.append({
                "id": f"g_{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
                "owner_id": player_id,
                "pos": list(pos),
                "vel": [forward[0] * 18.0, up, forward[2] * 18.0],
                "spawned_at": time.time(),
                "fuse": GRENADE_FUSE,
                "radius": GRENADE_RADIUS,
                "damage": GRENADE_DAMAGE,
            })
            self.events.append({"type": "grenade_spawn", "owner_id": player_id})
            return True

    def remove_player(self, player_id):
        with self.lock:
            if player_id in self.players:
                name = self.players[player_id]["name"]
                del self.players[player_id]
                self.events.append({"type": "leave", "player_id": player_id, "name": name})

    # ── per-frame updates from clients ────────

    def update_player_input(self, player_id, pos, rot, weapon="Assault Rifle"):
        with self.lock:
            p = self.players.get(player_id)
            if p and p["alive"]:
                p["pos"] = list(pos)
                p["rot"] = rot
                p["weapon"] = weapon

    def handle_shoot(self, shooter_id, target_id, damage=WEAPON_DAMAGE):
        with self.lock:
            if not target_id:
                return  # missed everyone
            shooter = self.players.get(shooter_id)
            target = self.players.get(target_id)
            if not shooter or not target:
                return
            if not shooter["alive"] or not target["alive"]:
                return

            target["hp"] = max(0, target["hp"] - damage)
            self.events.append({
                "type": "hit",
                "shooter": shooter_id,
                "shooter_name": shooter["name"],
                "target": target_id,
                "target_name": target["name"],
                "dmg": damage,
            })

            if target["hp"] <= 0:
                target["alive"] = False
                target["deaths"] += 1
                target["respawn_at"] = time.time() + RESPAWN_TIME
                shooter["kills"] += 1
                self.events.append({
                    "type": "kill",
                    "shooter": shooter_id,
                    "shooter_name": shooter["name"],
                    "target": target_id,
                    "target_name": target["name"],
                })

                self.spawn_heal_pickup(target["pos"])

                if shooter["kills"] >= self.kills_to_win and not self.match_over:
                    self.match_over = True
                    self.winner_id = shooter_id
                    self.winner_name = shooter["name"]
                    self.events.append({
                        "type": "match_end",
                        "winner_id": shooter_id,
                        "winner_name": shooter["name"],
                        "kills_to_win": self.kills_to_win,
                    })

    def force_respawn(self, player_id):
        with self.lock:
            p = self.players.get(player_id)
            if not p or p["alive"]:
                return False

            spawn = list(random.choice(SPAWN_POINTS))
            p["alive"] = True
            p["hp"] = PLAYER_MAX_HP
            p["pos"] = spawn
            p["rot"] = 0.0
            p["respawn_at"] = 0
            self.events.append({
                "type": "spawn",
                "player_id": player_id,
                "pos": spawn,
                "manual": True,
            })
            return True

    def apply_pickup_touch(self, player_id, pos):
        with self.lock:
            player = self.players.get(player_id)
            if not player or not player["alive"] or player["hp"] >= PLAYER_MAX_HP:
                return None

            taken = None
            px, py, pz = pos
            for pickup in list(self.pickups):
                dx = pickup["pos"][0] - px
                dy = pickup["pos"][1] - py
                dz = pickup["pos"][2] - pz
                if (dx * dx + dy * dy + dz * dz) ** 0.5 <= pickup["radius"]:
                    taken = pickup
                    self.pickups.remove(pickup)
                    player["hp"] = min(PLAYER_MAX_HP, player["hp"] + pickup["heal"])
                    self.events.append({
                        "type": "pickup_taken",
                        "pickup_id": pickup["id"],
                        "player_id": player_id,
                        "hp": player["hp"],
                    })
                    break
            return taken

    def _explode_grenade(self, grenade):
        owner = self.players.get(grenade["owner_id"])
        if not owner:
            return
        gx, gy, gz = grenade["pos"]
        for pid, player in self.players.items():
            if not player["alive"]:
                continue
            dx = player["pos"][0] - gx
            dy = player["pos"][1] - gy
            dz = player["pos"][2] - gz
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            if dist <= grenade["radius"]:
                damage = max(10, int(grenade["damage"] * (1.0 - (dist / grenade["radius"]))))
                player["hp"] = max(0, player["hp"] - damage)
                self.events.append({
                    "type": "grenade_hit",
                    "owner_id": grenade["owner_id"],
                    "target_id": pid,
                    "damage": damage,
                    "pos": list(grenade["pos"]),
                })
                if player["hp"] <= 0:
                    player["alive"] = False
                    player["deaths"] += 1
                    player["respawn_at"] = time.time() + RESPAWN_TIME
                    owner["kills"] += 1
                    self.spawn_heal_pickup(player["pos"])
                    self.events.append({
                        "type": "kill",
                        "shooter": grenade["owner_id"],
                        "shooter_name": owner["name"],
                        "target": pid,
                        "target_name": player["name"],
                    })
                    if owner["kills"] >= self.kills_to_win and not self.match_over:
                        self.match_over = True
                        self.winner_id = grenade["owner_id"]
                        self.winner_name = owner["name"]
                        self.events.append({
                            "type": "match_end",
                            "winner_id": grenade["owner_id"],
                            "winner_name": owner["name"],
                            "kills_to_win": self.kills_to_win,
                        })


    # ── tick (called by server tick thread) ────

    def reset_match(self):
        with self.lock:
            self.match_over = False
            self.winner_id = None
            self.winner_name = None
            self._restart_time = 0.0
            
            # Reset scores for all active players
            for pid, player in self.players.items():
                player["kills"] = 0
                player["deaths"] = 0
                player["hp"] = PLAYER_MAX_HP
                player["alive"] = True
                spawn = list(random.choice(SPAWN_POINTS))
                player["pos"] = spawn
                player["rot"] = 0.0
                player["respawn_at"] = 0
                
            self.pickups.clear()
            self.grenades.clear()
            self.events.append({
                "type": "match_start"
            })

    def update(self):
        with self.lock:
            now = time.time()

            # Match restart logic
            if self.match_over:
                if not hasattr(self, '_restart_time') or self._restart_time == 0.0:
                    self._restart_time = now + 10.0
                elif now >= self._restart_time:
                    self.reset_match()

            for pid, p in self.players.items():
                if not p["alive"] and now >= p["respawn_at"]:
                    spawn = list(random.choice(SPAWN_POINTS))
                    p["alive"] = True
                    p["hp"] = PLAYER_MAX_HP
                    p["pos"] = spawn
                    self.events.append({
                        "type": "spawn",
                        "player_id": pid,
                        "pos": spawn,
                    })

            self.pickups = [pickup for pickup in self.pickups if now - pickup["spawned_at"] < pickup["lifetime"]]

            new_grenades = []
            dt_grenades = 1.0 / 30.0
            for grenade in self.grenades:
                elapsed = now - grenade["spawned_at"]
                if elapsed >= grenade["fuse"]:
                    self._explode_grenade(grenade)
                    self.events.append({"type": "grenade_explode", "grenade_id": grenade["id"], "pos": list(grenade["pos"])})
                    continue
                
                vel = grenade["vel"]
                # Apply gravity
                vel[1] -= 28.0 * dt_grenades
                
                # Next position calculation
                next_pos = [
                    grenade["pos"][0] + vel[0] * dt_grenades,
                    grenade["pos"][1] + vel[1] * dt_grenades,
                    grenade["pos"][2] + vel[2] * dt_grenades
                ]

                # 1. Floor collision
                if next_pos[1] <= 0.15:
                    next_pos[1] = 0.15
                    vel[1] = -vel[1] * 0.45
                    vel[0] *= 0.7
                    vel[2] *= 0.7

                # 2. Boundary walls
                if next_pos[0] < -59.0:
                    next_pos[0] = -59.0
                    vel[0] = -vel[0] * 0.45
                elif next_pos[0] > 59.0:
                    next_pos[0] = 59.0
                    vel[0] = -vel[0] * 0.45

                if next_pos[2] < -59.0:
                    next_pos[2] = -59.0
                    vel[2] = -vel[2] * 0.45
                elif next_pos[2] > 59.0:
                    next_pos[2] = 59.0
                    vel[2] = -vel[2] * 0.45

                # 3. Static obstacle collisions (AABB check & bounce)
                for col in STATIC_COLLIDERS:
                    if (col["min"][0] <= next_pos[0] <= col["max"][0] and
                        col["min"][1] <= next_pos[1] <= col["max"][1] and
                        col["min"][2] <= next_pos[2] <= col["max"][2]):
                        
                        # Find minimum overlap axis to push it out and bounce
                        overlap_x = min(next_pos[0] - col["min"][0], col["max"][0] - next_pos[0])
                        overlap_y = min(next_pos[1] - col["min"][1], col["max"][1] - next_pos[1])
                        overlap_z = min(next_pos[2] - col["min"][2], col["max"][2] - next_pos[2])
                        
                        min_overlap = min(overlap_x, overlap_y, overlap_z)
                        
                        if min_overlap == overlap_y:
                            if vel[1] < 0:
                                next_pos[1] = col["max"][1] + 0.02
                            else:
                                next_pos[1] = col["min"][1] - 0.02
                            vel[1] = -vel[1] * 0.45
                            vel[0] *= 0.7
                            vel[2] *= 0.7
                        elif min_overlap == overlap_x:
                            if vel[0] < 0:
                                next_pos[0] = col["max"][0] + 0.02
                            else:
                                next_pos[0] = col["min"][0] - 0.02
                            vel[0] = -vel[0] * 0.45
                        else:
                            if vel[2] < 0:
                                next_pos[2] = col["max"][2] + 0.02
                            else:
                                next_pos[2] = col["min"][2] - 0.02
                            vel[2] = -vel[2] * 0.45

                grenade["pos"] = next_pos
                new_grenades.append(grenade)
            self.grenades = new_grenades

    def snapshot(self):
        """Return a deep-ish copy safe to serialize outside the lock."""
        with self.lock:
            import copy
            restart_in = 0.0
            if self.match_over and hasattr(self, '_restart_time') and self._restart_time > 0.0:
                restart_in = max(0.0, self._restart_time - time.time())

            return {
                "players": copy.deepcopy(self.players),
                "pickups": copy.deepcopy(self.pickups),
                "grenades": copy.deepcopy(self.grenades),
                "match_over": self.match_over,
                "winner_id": self.winner_id,
                "winner_name": self.winner_name,
                "kills_to_win": self.kills_to_win,
                "restart_in": restart_in,
            }

    def pop_events(self):
        with self.lock:
            evs = list(self.events)
            self.events.clear()
            return evs
