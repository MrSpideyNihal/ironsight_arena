# client/weapons.py
# ──────────────────────────────────────────────
# Hitscan weapon system.
#   • Raycasts from camera center + spread
#   • Muzzle-flash & impact-spark entities
#   • Bullet-trace via thin stretched cube
#   • Ammo tracking & reload timer
# ──────────────────────────────────────────────
import random
from ursina import (Entity, Vec3, color, camera, raycast, mouse,
                    destroy, time as ursina_time)
from config.settings import (
    WEAPON_AMMO_CAPACITY, WEAPON_RELOAD_TIME,
    WEAPON_FIRE_RATE, WEAPON_SPREAD, WEAPON_ADS_SPREAD,
    WEAPON_RECOIL_FORCE, WEAPON_CONFIGS
)


class Weapon(Entity):
    def __init__(self, owner, **kwargs):
        super().__init__(**kwargs)
        self.owner = owner
        self.weapon_name = "Assault Rifle"
        self.current_config = WEAPON_CONFIGS[self.weapon_name]
        self.ammo = self.current_config["max_ammo"]
        self.max_ammo = self.current_config["max_ammo"]
        self._cooldown = 0.0
        self._reloading = False
        self._reload_timer = 0.0
        self.ammo_multiplier = 1.0

    # ── Ursina calls this every frame ─────────

    def update(self):
        dt = ursina_time.dt
        if self._cooldown > 0:
            self._cooldown -= dt

        if self._reloading:
            self._reload_timer -= dt
            if self._reload_timer <= 0:
                self.ammo = self.max_ammo
                self._reloading = False
                self._notify_ammo()
                self._set_status("")

    # ── public API ────────────────────────────

    @property
    def is_reloading(self):
        return self._reloading

    def switch_to(self, name, force=False):
        if name not in WEAPON_CONFIGS:
            return
        if not force and name == self.weapon_name:
            return
        if self._reloading:
            self._reloading = False
            self._set_status("")

        self.weapon_name = name
        self.current_config = WEAPON_CONFIGS[name]

        if self.ammo_multiplier == 999.0:
            self.max_ammo = self.current_config["max_ammo"]
        else:
            self.max_ammo = int(self.current_config["max_ammo"] * self.ammo_multiplier)

        self.ammo = self.max_ammo
        self._cooldown = 0.0
        self._notify_ammo()

        # switch the visible gun model in FPP
        cam = self.owner.cam_ctrl
        if cam and hasattr(cam, 'switch_weapon_model'):
            cam.switch_weapon_model(name)

    def reload(self):
        if self._reloading or self.ammo == self.max_ammo or self.ammo_multiplier == 999.0:
            return
        self._reloading = True
        self._reload_timer = self.current_config["reload_time"]
        self._set_status("RELOADING...")

    def try_shoot(self, network):
        """Returns True if a shot was fired."""
        if self._cooldown > 0 or self._reloading:
            return False
        if self.ammo <= 0 and self.ammo_multiplier != 999.0:
            self.reload()
            return False

        if self.ammo_multiplier != 999.0:
            self.ammo -= 1
        self._cooldown = self.current_config["fire_rate"]
        self._notify_ammo()

        # expand crosshair on shoot
        if self.owner.hud:
            self.owner.hud.expand_crosshair()

        # ── spread ────────────────────────────
        spread = self.current_config["ads_spread"] if mouse.right else self.current_config["spread"]
        sx = random.uniform(-spread, spread)
        sy = random.uniform(-spread, spread)
        ray_dir = (camera.forward + camera.right * sx + camera.up * sy).normalized()

        # ── raycast ───────────────────────────
        ignore = [self.owner]
        for c in self.owner.children:
            ignore.append(c)

        ray = raycast(camera.world_position, ray_dir,
                      distance=120, ignore=ignore)

        hit_id = None
        end_point = camera.world_position + ray_dir * 120

        if ray.hit:
            end_point = ray.world_point
            self._impact_spark(end_point)

            hit_ent = ray.entity
            if hasattr(hit_ent, 'player_id') and hit_ent.player_id:
                hit_id = hit_ent.player_id
                # hit feedback
                if self.owner.hud:
                    self.owner.hud.flash_hit()

        # ── visuals ───────────────────────────
        self._muzzle_flash()
        self._bullet_trace(camera.world_position + camera.forward * 1.5, end_point)

        # ── network ──────────────────────────
        if network and network.joined:
            network.send({
                "type": "shoot",
                "player_id": self.owner.player_id,
                "target_id": hit_id,
                "damage": self.current_config["damage"]
            })

        # ── recoil ────────────────────────────
        cam = self.owner.cam_ctrl
        if cam:
            cam.add_recoil(self.current_config["recoil"])

        return True

    # ── visual helpers ────────────────────────

    def _muzzle_flash(self):
        conf = self.current_config
        flash = Entity(parent=self.owner, model='sphere',
                       color=color.rgb32(conf["color_r"], conf["color_g"], conf["color_b"]),
                       scale=conf["model_scale"], position=conf["muzzle_pos"])
        destroy(flash, delay=0.05)

    def _bullet_trace(self, start, end):
        conf = self.current_config
        diff = end - start
        dist = diff.length()
        if dist < 0.1:
            return
        mid = (start + end) * 0.5
        trace = Entity(model='cube',
                       color=color.rgba32(conf["trace_r"], conf["trace_g"], conf["trace_b"], conf["trace_a"]),
                       scale=(0.012, 0.012, dist),
                       position=mid)
        trace.look_at(end)
        destroy(trace, delay=0.07)

    def _impact_spark(self, pos):
        spark = Entity(model='sphere', color=color.rgb32(255, 220, 80),
                       scale=0.12, position=pos)
        destroy(spark, delay=0.12)

    # ── owner helpers (safe access) ───────────

    def _notify_ammo(self):
        if self.owner.hud:
            ammo_str = "INF" if self.ammo_multiplier == 999.0 else self.ammo
            max_ammo_str = "INF" if self.ammo_multiplier == 999.0 else self.max_ammo
            self.owner.hud.set_ammo(ammo_str, max_ammo_str, self.weapon_name)

    def _set_status(self, msg):
        if self.owner.hud:
            self.owner.hud.set_status(msg)
