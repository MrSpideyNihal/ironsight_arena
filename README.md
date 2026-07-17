# Ironsight Arena — Python LAN TPS

A server-authoritative 3rd-person LAN Arena Shooter built with Python, Ursina Engine, and raw UDP Sockets.

---

## Getting Started

### 1. Installation

Install the dependencies:
```bash
pip install -r requirements.txt
```

### 2. How to Play

Run the launcher script:
```bash
python main.py
```

- **Enter Nickname** in the top field.
- **To Host**: Click **Host Game**. This starts the server locally on port `5555` in a background thread and connects your client to it. It also broadcasts the server details on LAN.
- **To Join (Auto Discovery)**: Any clients on the same network running the game will see the host's server show up under **Discovered Servers on LAN**. Just click on the server button to join.
- **To Join (Direct IP)**: If discovery is blocked by your router settings, enter the host's local IP address (e.g. `192.168.1.15`) in the **Direct IP** input field and click **Direct Connect**.

### 3. Controls
- **W, A, S, D**: Move
- **Mouse**: Look / Aim camera
- **Left Click**: Shoot Weapon (Hold / Click)
- **Right Click (Hold)**: Aim Down Sights (ADS Zoom)
- **Spacebar**: Jump
- **R**: Reload weapon
- **TAB (Hold)**: View Scoreboard (Kills & Deaths stats)
- **Escape**: Exit Game window

---

## LAN Multiplayer Troubleshooting

LAN connection issues are almost always caused by system firewalls or router configurations:

1. **Firewall Settings**:
   On first run, Windows Firewall or macOS will ask to allow Python/the game to access the network. You **must** select both Private and Public network permissions.
   - If hosting, ensure port `5555` (UDP) and `5556` (UDP) are allowed in your antivirus/firewall configurations.

2. **Access Point (AP) Isolation / Client Isolation**:
   Many modern home/office routers or public hotspots (e.g. university/cafe WiFi) have **AP Isolation** enabled by default. This security feature prevents devices connected to the same WiFi router from communicating with each other.
   - **Fix**: Use a home router where AP Isolation can be disabled, create a mobile hotspot from one of the phones/laptops, or connect both machines using a wired Ethernet switch.

3. **Wrong Subnet**:
   Ensure both devices are connected to the exact same WiFi network (e.g., check that one device isn't on a `Guest` network and the other on the main network).
