# keyence_glr_ws

ROS 2 **Humble** workspace (source-only — build on the Jetson) that reads
per-beam status from a Keyence **GL-R52H** light curtain (52 optical axes) via
an **NU-EP1** EtherNet/IP unit and shows it on a live web dashboard.

## Packages

| Package | Purpose |
|---|---|
| `keyence_glr_msgs`   | `BeamStatus.msg`, `CurtainStatus.msg` |
| `keyence_glr_driver` | `nu_ep1_driver` (real, via pycomm3) + `mock_publisher` (sweep) |
| `keyence_glr_bringup`| rosbridge + static **raw-data** web view (`/gl_r/status` over ws://…/9090) |

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
Open `http://<jetson-ip>:8000/` — a "hand" sweeps across the 52 beams; the
page shows it as a live 0/1 bitmap (see below).

**Real GL-R52H via NU-EP1:**
```bash
# nu_ep1.yaml is preset for the GL-R52H (beam_count: 52). Before going live,
# confirm in src/keyence_glr_driver/config/nu_ep1.yaml:
#   ip_address (the GC1000/NU-EP1 IP, not the Jetson),
#   assembly_instance, assembly_size  (from your NU-EP1 EDS)
ros2 launch keyence_glr_bringup demo.launch.py use_mock:=false
```

## Web view (raw `/gl_r/status`)

`http://<jetson-ip>:8000/` is a technical, no-frills view of the raw message
(it subscribes over rosbridge `ws://<host>:9090`). No mapping/processing — just
what the driver publishes:

- **beam bitmap** — every optical axis as `index` + `0/1` (1 = blocked),
  coloured by `health` (clear / blocked / stale / fault)
- **fields** — `stamp`, `frame_id`, `beam_count`, `ossd_a/b`, `lockout`,
  `muted`, `any_blocked`, `blocked_count` as raw values
- **bitmap bytes** — beams re-packed to bytes (LSB = beam 0) shown in **hex**
  and **binary**, matching the NU-EP1 byte layout below — handy for confirming
  a GC-1000/NU-EP1 assembly layout
- **raw message** — the full `CurtainStatus` as JSON (throttled)
- header pills: connection, real **Hz**, and message **age** (red if the
  stream stalls > 500 ms)

The UI lives in `src/keyence_glr_bringup/web/` (`index.html`, `app.js`,
`style.css`).

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

  The NU-EP1 bitmap is a fixed 8 bytes (64 bits); the GL-R52H uses the low
  52 bits and `beam_count: 52` ignores the unused top bits. If your EDS
  differs, adjust `AssemblyLayout` and the bit positions (`STATUS_*`) —
  that's the only place the byte parsing lives.

## Dev on this (non-Jetson) box

You picked "pure source workspace, no build here", so don't `colcon build`
locally — the workspace exists only to be moved. To eyeball the dashboard
UI without ROS, you can open `src/keyence_glr_bringup/web/index.html` in a
browser; it will show "disconnected" until a rosbridge is reachable.
