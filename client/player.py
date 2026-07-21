# client/player.py
# ──────────────────────────────────────────────
# Player entity classes.
#   LocalPlayer  — client-side predicted, sends
#                  inputs to server each frame.
#   RemotePlayer — interpolates toward the latest
#                  server snapshot.
# ──────────────────────────────────────────────
import os
from ursina import (Entity, Vec3, color, held_keys, mouse,
                    raycast, destroy, Text, time as ursina_time, scene)
from config.settings import (
    MOVE_SPEED, SPRINT_SPEED, GRAVITY, JUMP_FORCE, PLAYER_MAX_HP, GROUND_RAY_DIST,
    GRENADE_COOLDOWN, DASH_DURATION, DASH_COOLDOWN, DASH_SPEED_MULTIPLIER,
)
from client.weapons import Weapon

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AR_OBJ = os.path.join(_PROJECT_ROOT, "assest", "noramlgun", "obj", "m4a1_s.obj")
_AR_TEX = os.path.join(_PROJECT_ROOT, "assest", "noramlgun", "obj", "M4A1-s.tga")
_SR_OBJ = os.path.join(_PROJECT_ROOT, "assest", "sniper", "scifi_gun.obj")


def _try_load_np(abs_path, texture_path=None):
    """Load a model via native Panda3D loader; returns NodePath or None."""
    try:
        from panda3d.core import Filename, get_model_path
        # Convert OS absolute path to Panda3D path format
        panda_path = Filename.fromOsSpecific(abs_path).getFullpath()
        folder = os.path.dirname(panda_path)
        get_model_path().prepend_path(folder)
        np = base.loader.loadModel(panda_path)
        if np and texture_path:
            tex_panda = Filename.fromOsSpecific(texture_path).getFullpath()
            tex = base.loader.loadTexture(tex_panda)
            if tex:
                np.setTexture(tex, 1)
        return np
    except Exception as e:
        print(f"[Player] model load failed {abs_path}: {e}")
        return None


def _get_all_descendants(entity):
    """Recursively collect all children, grandchildren, etc. of an entity."""
    descendants = []
    if hasattr(entity, 'children'):
        for c in entity.children:
            descendants.append(c)
            descendants.extend(_get_all_descendants(c))
    return descendants


# ──────────────────────────────────────────────
#  Base (shared visuals & identity)
# ──────────────────────────────────────────────
class _BasePlayer(Entity):
    def __init__(self, player_id, name="Player", is_local=False, **kw):
        # Tactical dark colors instead of bright red/blue blocks
        body_col = color.rgb32(30, 80, 140) if is_local else color.rgb32(140, 40, 40)
        super().__init__(
            model='cube',
            color=body_col,
            scale=(0.9, 1.8, 0.9),
            collider='box',
            **kw,
        )
        self.player_id = player_id
        self.player_name = name
        self.is_local = is_local
        self.hp = PLAYER_MAX_HP
        self.alive = True
        self.color_idx = 0

        # ── head ──────────────────────────────
        self.head = Entity(parent=self, model='sphere',
                           color=color.rgb32(200, 200, 210),
                           scale=(0.65, 0.55, 0.65),
                           position=(0, 0.85, 0))
        self.head.no_damage_zone = True
        # visor
        Entity(parent=self.head, model='cube',
               color=color.rgb32(20, 20, 25),
               scale=(0.75, 0.22, 0.25),
               position=(0, 0.08, 0.4))

        # ── name tag (billboard) ──────────────
        self.tag = Text(parent=self, text=name,
                        billboard=True,
                        scale=12,
                        y=1.6,
                        origin=(0, 0),
                        color=color.rgb32(255, 255, 100) if is_local else color.white,
                        enabled=not is_local)

        # ── shoulder pads ─────────────────────
        for sx in (-0.55, 0.55):
            Entity(parent=self, model='cube',
                   color=color.rgb32(60, 65, 80),
                   scale=(0.3, 0.15, 0.45),
                   position=(sx, 0.42, 0))

        # ── belt ──────────────────────────────
        Entity(parent=self, model='cube',
               color=color.rgb32(40, 42, 48),
               scale=(1.02, 0.08, 1.02),
               position=(0, -0.1, 0))

        # ── boots ─────────────────────────────
        for bx in (-0.2, 0.2):
            Entity(parent=self, model='cube',
                   color=color.rgb32(35, 35, 40),
                   scale=(0.35, 0.2, 0.5),
                   position=(bx, -0.50, 0.05))

        # ── third-person weapon model (held in right hand) ──
        # Load with texture so it's not plain white
        self.tpp_weapon_np = _try_load_np(_AR_OBJ, _AR_TEX)
        if self.tpp_weapon_np:
            self.tpp_weapon_np.reparentTo(self)
            self.tpp_weapon_np.setScale(0.009)
            self.tpp_weapon_np.setPos(0.30, -0.12, 0.40)
            # H=0: barrel into screen; no roll
            self.tpp_weapon_np.setHpr(0, 0, 0)
        else:
            self.tpp_weapon_np = Entity(
                parent=self, model='cube',
                color=color.rgb32(75, 75, 85),
                scale=(0.05, 0.05, 0.40),
                position=(0.30, -0.12, 0.30),
            )
        self._tpp_weapon_name = "Assault Rifle"

        # ── weapon logic entity ───────────────
        self.weapon = Weapon(owner=self)
        self.hud = None       # set by client after construction
        self.cam_ctrl = None   # set by client after construction

        # Floating enemy health bar (visual only, for remote players)
        if not is_local:
            self.hp_bar_bg = Entity(parent=self, model='quad', color=color.rgba32(100, 10, 10, 180),
                                    scale=(0.8, 0.08), position=(0, 2.0, 0), billboard=True)
            self.hp_bar_fill = Entity(parent=self.hp_bar_bg, model='quad', color=color.rgb32(50, 220, 90),
                                      scale=(0.96, 0.8), position=(-0.48, 0, -0.01), origin_x=-0.5)

    def update_weapon_visual(self, weapon_name):
        if getattr(self, '_tpp_weapon_name', None) == weapon_name:
            return
        self._tpp_weapon_name = weapon_name

        # Remove old
        if hasattr(self, '_tpp_extra_np') and self._tpp_extra_np:
            try:
                self._tpp_extra_np.removeNode()
            except Exception:
                try:
                    destroy(self._tpp_extra_np)
                except Exception:
                    pass
            self._tpp_extra_np = None

        # Hide primary
        if hasattr(self, 'tpp_weapon_np') and self.tpp_weapon_np:
            try:
                self.tpp_weapon_np.hide()
            except Exception:
                try:
                    self.tpp_weapon_np.enabled = False
                except Exception:
                    pass

        if weapon_name == "Sniper Rifle":
            sr = _try_load_np(_SR_OBJ)
            if sr:
                sr.reparentTo(self)
                sr.setScale(0.006)
                sr.setPos(0.30, -0.12, 0.42)
                # H=0: barrel into screen; no roll
                sr.setHpr(0, 0, 0)
                sr.setColorScale(0.28, 0.30, 0.35, 1)
                self._tpp_extra_np = sr
            else:
                self._tpp_extra_np = Entity(
                    parent=self, model='cube',
                    color=color.rgb32(45, 120, 200),
                    scale=(0.04, 0.05, 0.48),
                    position=(0.30, -0.12, 0.34),
                )
        else:
            # Show AR again
            if hasattr(self, 'tpp_weapon_np') and self.tpp_weapon_np:
                try:
                    self.tpp_weapon_np.show()
                except Exception:
                    try:
                        self.tpp_weapon_np.enabled = True
                    except Exception:
                        pass

    def set_color_from_idx(self, idx):
        from config.settings import PLAYER_COLORS
        self.color_idx = idx
        if 0 <= idx < len(PLAYER_COLORS):
            rgb = PLAYER_COLORS[idx]
            self.color = color.rgb32(*rgb)

    def set_hp_visual(self, hp):
        self.hp = hp
        if not self.is_local and hasattr(self, 'hp_bar_fill'):
            ratio = max(0.0, min(1.0, hp / PLAYER_MAX_HP))
            self.hp_bar_fill.scale_x = 0.96 * ratio

    def die(self):
        self.alive = False
        self.visible = False
        self.collider = None
        for c in self.children:
            c.enabled = False

    def respawn_at(self, pos):
        self.alive = True
        self.hp = PLAYER_MAX_HP
        self.position = Vec3(*pos) if not isinstance(pos, Vec3) else pos
        self.visible = True
        self.collider = 'box'
        # Reset physics so old fall velocity doesn't carry over
        if hasattr(self, 'vel_y'):
            self.vel_y = 0.0
        if hasattr(self, 'grounded'):
            self.grounded = False
        for c in self.children:
            c.enabled = True
        if not self.is_local and hasattr(self, 'hp_bar_fill'):
            self.hp_bar_fill.scale_x = 0.96

    def cleanup(self):
        destroy(self.weapon)
        destroy(self)


# ──────────────────────────────────────────────
#  Local Player (client-side prediction)
# ──────────────────────────────────────────────
class LocalPlayer(_BasePlayer):
    def __init__(self, player_id, name, network, **kw):
        super().__init__(player_id, name, is_local=True, **kw)
        self.network = network
        self.vel_y = 0.0
        self.grounded = False
        self.speed_multiplier = 1.0
        self._jump_was_down = False
        self._respawn_was_down = False
        self._dash_was_down = False
        self._dash_timer = 0.0
        self._dash_cooldown = 0.0
        self._grenade_cooldown = 0.0
        self.climbing = False

    def update(self):
        respawn_down = held_keys['k']
        if not self.alive:
            if respawn_down and not self._respawn_was_down and self.network and self.network.running:
                self.network.send({
                    "type": "respawn",
                    "player_id": self.player_id,
                })
            self._respawn_was_down = respawn_down
            return

        dt = ursina_time.dt

        if self._dash_timer > 0:
            self._dash_timer = max(0.0, self._dash_timer - dt)
        if self._dash_cooldown > 0:
            self._dash_cooldown = max(0.0, self._dash_cooldown - dt)
        if self._grenade_cooldown > 0:
            self._grenade_cooldown = max(0.0, self._grenade_cooldown - dt)

        # ── build ignore list for raycasts ────
        ignore = [self] + _get_all_descendants(self)

        # Ignore other player entities (and all their sub-entities recursively)
        # to prevent getting stuck in them or blocked by their visual parts.
        for ent in scene.entities:
            if hasattr(ent, 'player_id') and ent.player_id and ent != self:
                ignore.append(ent)
                ignore.extend(_get_all_descendants(ent))

        # ── ladder climbing detection ─────────
        near_ladder = False
        ladder_ent = None
        for ent in scene.entities:
            if getattr(ent, 'is_ladder', False):
                dist_xz = ((ent.x - self.x)**2 + (ent.z - self.z)**2)**0.5
                if dist_xz < 1.35 and abs(ent.y - self.y) < (ent.scale_y / 2.0 + 1.2):
                    near_ladder = True
                    ladder_ent = ent
                    break

        if not near_ladder:
            self.climbing = False
        else:
            # If pressing W or S near a ladder, start climbing
            if held_keys['w'] or held_keys['s']:
                self.climbing = True

        # ── horizontal movement ───────────────
        speed = SPRINT_SPEED if held_keys['left shift'] else MOVE_SPEED
        speed *= self.speed_multiplier
        if self._dash_timer > 0:
            speed *= DASH_SPEED_MULTIPLIER
        
        # Slower movement on ladder
        if self.climbing:
            speed *= 0.5

        direction = Vec3(0, 0, 0)
        # In climbing mode, W/S moves vertically, so they do not produce horizontal movement
        if not self.climbing:
            if held_keys['w']:
                direction += self.forward
            if held_keys['s']:
                direction -= self.forward
        if held_keys['a']:
            direction -= self.right
        if held_keys['d']:
            direction += self.right

        direction.y = 0
        if direction.length() > 0:
            direction = direction.normalized()

        move = direction * speed * dt

        # ── wall collision (X then Z check at multiple heights) ──
        # Cast at feet (0.2), waist (0.9), and chest (1.6) to prevent clipping low/tall objects
        heights = [0.2, 0.9, 1.6]
        if move.x != 0:
            blocked = False
            for h in heights:
                origin = self.position + Vec3(0, h, 0)
                ray = raycast(origin, Vec3(move.x, 0, 0).normalized(),
                              distance=abs(move.x) + 0.45, ignore=ignore)
                if ray.hit:
                    blocked = True
                    break
            if blocked:
                move.x = 0

        if move.z != 0:
            blocked = False
            for h in heights:
                origin = self.position + Vec3(0, h, 0)
                ray = raycast(origin, Vec3(0, 0, move.z).normalized(),
                              distance=abs(move.z) + 0.45, ignore=ignore)
                if ray.hit:
                    blocked = True
                    break
            if blocked:
                move.z = 0

        self.position += Vec3(move.x, 0, move.z)

        # ── dash ability ──────────────────────
        dash_down = held_keys['f']
        if dash_down and not self._dash_was_down and self._dash_cooldown <= 0 and direction.length() > 0 and not self.climbing:
            self._dash_timer = DASH_DURATION
            self._dash_cooldown = DASH_COOLDOWN
            if self.hud:
                self.hud.flash_dash()
        self._dash_was_down = dash_down

        # ── gravity / climbing / jumping ──────
        jump_down = held_keys['space']

        if self.climbing:
            self.vel_y = 0.0
            self.grounded = True
            
            # Jump off the ladder
            if jump_down and not self._jump_was_down:
                self.climbing = False
                self.vel_y = JUMP_FORCE
                self.grounded = False
                # push back slightly from ladder
                self.position -= self.forward * 0.8
            else:
                climb_speed = 5.0
                if held_keys['w']:
                    self.y += climb_speed * dt
                elif held_keys['s']:
                    self.y -= climb_speed * dt
        else:
            # Normal gravity and jumping
            if not self.grounded:
                self.vel_y -= GRAVITY * dt
            else:
                self.vel_y = max(0, self.vel_y)
                if jump_down and not self._jump_was_down:
                    self.vel_y = JUMP_FORCE
                    self.grounded = False

            self.y += self.vel_y * dt

            # ── ground detection & snapping ───────
            if self.vel_y <= 0:
                ray_origin = self.position + Vec3(0, 0.5, 0)
                # longer raycast if already grounded to stick to downward slopes smoothly
                ray_dist = 2.0 if self.grounded else 1.4
                ground = raycast(ray_origin, Vec3(0, -1, 0), distance=ray_dist, ignore=ignore)
                if ground.hit:
                    target_y = ground.world_point.y + 0.9
                    if self.y <= target_y + 0.05 or self.grounded:
                        self.y = target_y
                        self.vel_y = 0.0
                        self.grounded = True
                    else:
                        self.grounded = False
                else:
                    self.grounded = False
            else:
                self.grounded = False

        self._jump_was_down = jump_down

        # ── fall-off reset ────────────────────
        if self.y < -20:
            import random
            from config.settings import SPAWN_POINTS
            sp = random.choice(SPAWN_POINTS)
            self.position = Vec3(*sp)
            self.vel_y = 0
            self.grounded = False

        # ── weapon switching ──────────────────
        if held_keys['1']:
            self.weapon.switch_to("Assault Rifle")
            self.update_weapon_visual("Assault Rifle")
        elif held_keys['2']:
            self.weapon.switch_to("Sniper Rifle")
            self.update_weapon_visual("Sniper Rifle")

        # ── grenade ability ───────────────────
        grenade_down = held_keys['g']
        if grenade_down and not getattr(self, '_grenade_was_down', False) and self._grenade_cooldown <= 0:
            self._grenade_cooldown = GRENADE_COOLDOWN
            if self.network and self.network.running:
                self.network.send({
                    "type": "ability",
                    "ability": "grenade",
                    "player_id": self.player_id,
                    "pos": [self.x, self.y + 1.0, self.z],
                    "rot": self.rotation_y,
                    "forward": [self.forward.x, self.forward.y, self.forward.z],
                    "up": 5.0,
                })
        self._grenade_was_down = grenade_down

        # ── shooting ─────────────────────────
        if mouse.left:
            self.weapon.try_shoot(self.network)
        if held_keys['r']:
            self.weapon.reload()

        # ── send position to server ──────────
        if self.network and self.network.running:
            self.network.send({
                "type": "input",
                "player_id": self.player_id,
                "pos": [self.x, self.y, self.z],
                "rot": self.rotation_y,
                "weapon": self.weapon.weapon_name,
            })

        self._respawn_was_down = respawn_down


    def respawn_at(self, pos):
        super().respawn_at(pos)
        self.vel_y = 0.0
        self._respawn_was_down = False
        self._jump_was_down = False
        self._dash_was_down = False
        self._dash_timer = 0.0
        self._dash_cooldown = 0.0
        self._grenade_cooldown = 0.0


# ──────────────────────────────────────────────
#  Remote Player (server-state interpolation)
# ──────────────────────────────────────────────
class RemotePlayer(_BasePlayer):
    def __init__(self, player_id, name, **kw):
        super().__init__(player_id, name, is_local=False, **kw)
        self.target_pos = Vec3(0, 0, 0)
        self.target_rot = 0.0

    def update(self):
        dt = ursina_time.dt
        if not self.alive:
            return
        # Adaptive lerp: faster when far from target, smooth when close
        dist = (self.target_pos - self.position).length()
        lerp_speed = 10.0 + dist * 2.0  # 10 at dist=0, 30 at dist=10
        lerp_speed = min(30.0, lerp_speed)
        self.position += (self.target_pos - self.position) * min(1.0, lerp_speed * dt)
        # shortest-path rotation lerp
        diff = (self.target_rot - self.rotation_y + 180) % 360 - 180
        self.rotation_y += diff * min(1.0, lerp_speed * dt)
