# main.py
# ──────────────────────────────────────────────
# Entry point for Ironsight Arena.
# Shows the menu, optionally starts a server
# thread if hosting, then runs the Ursina loop.
# ──────────────────────────────────────────────
import sys
import os
import threading
import time as std_time

# ── CRITICAL: set working directory to the folder
#    containing main.py, so that all relative imports
#    and Ursina asset lookups work regardless of how
#    the script is launched ─────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(_THIS_DIR)
sys.path.insert(0, _THIS_DIR)

# PyInstaller onefile support
if getattr(sys, '_MEIPASS', None):
    sys.path.insert(0, sys._MEIPASS)

from ursina import Ursina, window, color, camera, scene

from server.server import ArenaServer
from client.client import GameClient
from config.settings import SERVER_PORT

client = None
_server = None


def update():
    if client:
        try:
            client.update()
        except Exception as e:
            print(f"[Update Error] {e}")


def _start_server(nickname, server_name=None, speed_mult=1.0, ammo_mult=1.0, kills_to_win=10):
    global _server
    srv_name = server_name if server_name else f"{nickname}'s Server"
    _server = ArenaServer(host_name=srv_name, speed_mult=speed_mult, ammo_mult=ammo_mult, kills_to_win=kills_to_win)
    _server.start()


def _ensure_firewall():
    import ctypes, sys, os, subprocess

    if os.name != 'nt':
        return True

    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False

    ports = "7777-7787"
    rule_name = "Ironsight Arena"
    netsh_cmd = (
        f'netsh advfirewall firewall add rule name="{rule_name}" '
        f'dir=in protocol=udp localport={ports} action=allow'
    )

    # Try to create rule
    if is_admin:
        try:
            r = subprocess.run(netsh_cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                print(f"[System] Firewall rule '{rule_name}' created (UDP {ports}).", flush=True)
                return True
            else:
                print(f"[System] netsh failed: {r.stderr.strip()}", flush=True)
        except Exception as e:
            print(f"[System] Firewall setup failed: {e}", flush=True)
    else:
        if not getattr(sys, '_firewall_prompted', False):
            sys._firewall_prompted = True
            try:
                print("[System] Requesting admin to open UDP ports 7777-7787...", flush=True)
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "cmd.exe",
                    f'/c {netsh_cmd} & echo Rule created. & timeout /t 3',
                    None, 1
                )
                if ret <= 32:
                    print(f"[System] UAC elevation failed (code={ret}).", flush=True)
            except Exception as e:
                print(f"[System] UAC error: {e}", flush=True)

    print(f"[System] ╔══════════════════════════════════════════════════╗", flush=True)
    print(f"[System] ║   GUEST CANNOT JOIN? Run ONE command as Admin:  ║", flush=True)
    print(f"[System] ║                                                ║", flush=True)
    print(f"[System] ║   {netsh_cmd:<50} ║", flush=True)
    print(f"[System] ║                                                ║", flush=True)
    print(f"[System] ║   Or just run the game as Administrator.       ║", flush=True)
    print(f"[System] ╚══════════════════════════════════════════════════╝", flush=True)
    return False


def main():
    global client
    _ensure_firewall()
    app = Ursina(
        title="Ironsight Arena",
        borderless=False,
        fullscreen=False,
        show_ursina_logo=False,
        development_mode=False,
    )
    window.fps_counter.enabled = False
    window.cog_button.enabled = False
    window.exit_button.enabled = True
    window.color = color.rgb32(18, 20, 28)       # window clear color (dark)
    camera.orthographic = False

    client = GameClient()

    # ── wrap menu callbacks so we can inject
    #    the server thread when hosting ────────
    _original_host = client.host_game

    def on_host(nickname, server_name, speed_mult=1.0, ammo_mult=1.0, color_idx=0, kills_to_win=10):
        _start_server(nickname, server_name, speed_mult, ammo_mult, kills_to_win)
        client.selected_color_idx = color_idx
        # Wait for server to be ready with retries
        for _ in range(10):
            if _server and _server.running:
                break
            std_time.sleep(0.1)
        actual_port = _server.port if _server else SERVER_PORT
        std_time.sleep(0.2)
        _original_host(nickname, port=actual_port)

    if client.menu:
        client.menu.on_host_cb = on_host

    app.run()

    # cleanup
    if client:
        client.shutdown()
    if _server:
        _server.stop()


if __name__ == "__main__":
    main()
