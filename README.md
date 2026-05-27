# keyence_glr_ws

ROS 2 **Humble** workspace (source-only — build on the Jetson) that reads
per-beam status from a Keyence GL-R light curtain via an **NU-EP1** EtherNet/IP
unit and shows it on a live web dashboard.

## Packages

| Package | Purpose |
|---|---|
| `keyence_glr_msgs`   | `BeamStatus.msg`, `CurtainStatus.msg` |
| `keyence_glr_driver` | `nu_ep1_driver` (real, via pycomm3) + `mock_publisher` (sweep) |
| `keyence_glr_bringup`| rosbridge + static web dashboard (`/gl_r/status` over ws://…/9090) |

Topic: `/gl_r/status`  (`keyence_glr_msgs/msg/CurtainStatus`, ~20 Hz)

## Build on the Jetson (JetPack 5.x · Ubuntu 22.04 · ROS 2 Humble)

```bash
sudo apt update
sudo apt install -y ros-humble-rosbridge-server python3-pip python3-colcon-common-extensions
pip3 install --user pycomm3

cd ~/keyence_glr_ws
rosdep install --from-paths src --ignore-src -r -y   # optional, msgs only
colcon build --symlink-install
source install/setup.bash
```

## Run the demo

**Mock (no hardware needed):**
```bash
ros2 launch keyence_glr_bringup demo.launch.py use_mock:=true
```
Open `http://<jetson-ip>:8000/` — a "hand" sweeps across the 64 beams.

**Real GL-R via NU-EP1:**
```bash
# Edit src/keyence_glr_driver/config/nu_ep1.yaml first:
#   ip_address, assembly_instance, assembly_size  (from your NU-EP1 EDS)
ros2 launch keyence_glr_bringup demo.launch.py use_mock:=false
```

## NU-EP1 wiring you must verify

`nu_ep1_driver` reads `Assembly object (0x04) / instance N / attribute 3`
via unconnected explicit messaging. Three things come from your NU-EP1
EDS / setup software and must match `nu_ep1.yaml`:

- **`assembly_instance`** — the *input* assembly instance id (often 100/101).
- **`assembly_size`** — total bytes returned by that assembly.
- **byte layout** — `AssemblyLayout` in `nu_ep1_driver.py` assumes:
  - bytes 0–1 : status word (OSSD A/B, lockout, muted bits)
  - bytes 2–9 : 64-bit beam bitmap, LSB = beam 0
  - bytes 10–11 : blocked-beam count (u16)

  If your EDS differs, adjust `AssemblyLayout` and the bit positions
  (`STATUS_*`) — that's the only place the byte parsing lives.

## Dev on this (non-Jetson) box

You picked "pure source workspace, no build here", so don't `colcon build`
locally — the workspace exists only to be moved. To eyeball the dashboard
UI without ROS, you can open `src/keyence_glr_bringup/web/index.html` in a
browser; it will show "disconnected" until a rosbridge is reachable.
