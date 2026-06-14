# LEGO Sorter V2 — ROS 2 Jazzy on Raspberry Pi 5

> **Hardware:** [Basically LEGO Sorter V2](https://basically.website/sorter-v2) — three-stage
> singulation carousel, each stage driven by a NEMA17 42-40 stepper motor via A4988/DRV8825 driver.
> **Platform:** Raspberry Pi 5, ROS 2 Jazzy, Python, `lgpio`.

---

## Repository Layout

```
lego_sorter_ros2/
├── src/
│   ├── lego_sorter_msgs/          # Custom message types (PartReady, etc.)
│   │   ├── msg/
│   │   │   ├── PartReady.msg
│   │   │   ├── RecognitionResult.msg
│   │   │   ├── BinAssignment.msg
│   │   │   └── PartZone.msg
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   └── singulation_controller/    # Stepper motor controller package
│       ├── singulation_controller/
│       │   ├── __init__.py
│       │   └── stepper_node.py    # Main ROS 2 node
│       ├── launch/
│       │   ├── singulation_all.launch.py     # All 3 motors
│       │   └── singulation_single.launch.py  # One motor (testing)
│       ├── config/
│       │   └── motors.yaml        # Default pin/speed config
│       ├── resource/singulation_controller
│       ├── package.xml
│       ├── setup.py
│       └── setup.cfg
└── README.md
```

---

## Pipeline Architecture (from project doc)

The seven-node minimum viable network this package slots into:

```
camera_ros ──────────────────────────────────────────────┐
breakbeam_tracker → /singulation/part_ready              │
                  → /tracking/part_zone                  │
inspection_snapshot ← /singulation/part_ready            │
                    → /inspection/part_image             │
brickognize_recognizer ← /inspection/part_image         │
                       → /recognition/result             │
bin_router ← /recognition/result                        │
           → /routing/assignment                         │
diverter_controller ← /routing/assignment               │
                    ← /tracking/part_zone               │
bin_monitor → /bins/status                              │
                                                         │
singulation_controller (this package) ──────────────────┘
  Publishes:  /singulation/motor_N/status
              /singulation/part_ready  (synthetic, for testing)
  Subscribes: /singulation/motor_N/set_speed     (Float64, RPM)
              /singulation/motor_N/set_enable     (Bool)
              /singulation/motor_N/set_direction  (Bool, True=CW)
```

---

## Hardware: Wiring A4988 / DRV8825 → Pi 5 GPIO → NEMA17

### Bill of Materials (per motor)

| Qty | Part |
|-----|------|
| 1 | NEMA17 42-40 stepper motor |
| 1 | A4988 **or** DRV8825 stepper driver breakout |
| 1 | 12 V / 2 A power supply (barrel jack) |
| — | Jumper wires |
| 1 | 100 µF electrolytic capacitor (across VMOT/GND on driver) |

> ⚠️ **Never connect or disconnect the motor while the driver is powered.**
> This kills A4988/DRV8825 ICs instantly.

---

### Wiring Diagram (Motor 1 — default pins)

```
Raspberry Pi 5 (BCM)          A4988 / DRV8825            NEMA17
──────────────────────         ──────────────────         ──────────
GPIO 17 (STEP)   ─────────→   STEP
GPIO 27 (DIR)    ─────────→   DIR
GPIO 22 (EN)     ─────────→   ENABLE
3V3              ─────────→   VDD  (logic power)
GND              ─────────→   GND  (logic ground)
                              VMOT ←──────────  12V PSU (+)
                              GND  ←──────────  12V PSU (-)
                                    ╔══════════ 100µF cap across VMOT/GND
                              1A   ──┐
                              1B   ──┤  Coil A    Motor 4-wire
                              2A   ──┤  Coil B    (see coil ID below)
                              2B   ──┘
```

#### Identifying NEMA17 coil pairs with a multimeter

Set to resistance (Ω). Pairs that show ~2–10 Ω continuity are one coil.

```
Wire colours (common, not universal):
  Coil A: Red / Green
  Coil B: Yellow / Blue

If colours differ, probe: resistance between same-coil wires ≈ 3–5 Ω
                          resistance between different coils = ∞
```

---

### Pin Assignments for All Three Motors

Edit `config/motors.yaml` or override at launch if these don't match your wiring.

| Motor | Role | STEP (BCM) | DIR (BCM) | EN (BCM) |
|-------|------|-----------|-----------|---------|
| motor_1 | Bottom rotor | **17** | **27** | **22** |
| motor_2 | Middle rotor | **23** | **24** | **25** |
| motor_3 | Top rotor    | **5**  | **6**  | **13** |

---

### Current Limiting (A4988)

The NEMA17 42-40 is typically rated 1.5–1.7 A/phase. Set Vref on the driver potentiometer:

```
A4988:   Vref = I_peak × 8 × R_sense
         (most cheap breakouts: R_sense = 0.1 Ω → Vref = 0.8 V for 1.0 A)

DRV8825: Vref = I_peak / 2
         (for 1.0 A → Vref = 0.5 V)

Measure Vref between the pot wiper and GND while driver is powered (no motor).
Start low (0.3 V) and increase until motor has enough torque without overheating.
```

---

## Software Setup

### 1. System dependencies (on Pi 5)

```bash
# Update first
sudo apt update && sudo apt upgrade -y

# lgpio — Pi 5 compatible GPIO library
sudo apt install -y python3-lgpio lgpio

# ROS 2 Jazzy Python deps (should already be installed with ROS 2)
sudo apt install -y \
    python3-rclpy \
    ros-jazzy-std-msgs \
    ros-jazzy-launch-ros

# For building lego_sorter_msgs
sudo apt install -y \
    ros-jazzy-rosidl-default-generators \
    ros-jazzy-rosidl-default-runtime
```

### 2. GPIO permissions (avoid sudo for lgpio)

```bash
# Add your user to the gpio group
sudo usermod -aG gpio $USER
sudo usermod -aG dialout $USER

# Apply without reboot (or just reboot)
newgrp gpio
```

### 3. Clone and build

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone https://github.com/ChaosBuster/lego_sorter_ros2.git

cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash

# Build custom messages first, then controller
colcon build --packages-select lego_sorter_msgs
colcon build --packages-select singulation_controller

source install/setup.bash
```

---

## Running the Nodes

### Quick single-motor test (first bring-up)

```bash
source ~/ros2_ws/install/setup.bash

ros2 launch singulation_controller singulation_single.launch.py \
    motor_name:=motor_1 \
    step_pin:=17 \
    dir_pin:=27 \
    enable_pin:=22 \
    speed_rpm:=5.0
```

You should hear and feel the motor stepping. If not, re-check wiring.

### All three motors

```bash
ros2 launch singulation_controller singulation_all.launch.py speed_rpm:=10.0
```

---

## Runtime Control via ROS Topics

All topics are namespaced per motor: `/singulation/motor_N/...`

### Change speed (RPM) at runtime

```bash
# Set motor_1 to 20 RPM
ros2 topic pub --once /singulation/motor_1/set_speed std_msgs/msg/Float64 "data: 20.0"

# Stop motor_2 (0 RPM — motor stays enabled/holding)
ros2 topic pub --once /singulation/motor_2/set_speed std_msgs/msg/Float64 "data: 0.0"
```

### Enable / disable motor

```bash
# Disable (motor coils de-energised — free to spin by hand)
ros2 topic pub --once /singulation/motor_1/set_enable std_msgs/msg/Bool "data: false"

# Re-enable
ros2 topic pub --once /singulation/motor_1/set_enable std_msgs/msg/Bool "data: true"
```

### Reverse direction

```bash
# False = counter-clockwise
ros2 topic pub --once /singulation/motor_1/set_direction std_msgs/msg/Bool "data: false"
```

### Monitor status

```bash
# Live status at 1 Hz (JSON)
ros2 topic echo /singulation/motor_1/status

# Part-ready events
ros2 topic echo /singulation/part_ready
```

---

## ROS Parameter Reference

All parameters are settable at launch via `-p key:=value` or in a YAML override.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `motor_name` | string | `motor_1` | Logical name; used in topic namespace |
| `step_pin` | int | `17` | BCM GPIO → STEP pin on driver |
| `dir_pin` | int | `27` | BCM GPIO → DIR pin |
| `enable_pin` | int | `22` | BCM GPIO → ENABLE pin (active LOW) |
| `steps_per_rev` | int | `200` | Full steps per revolution (1.8° motor = 200) |
| `microstepping` | int | `1` | Divisor: 1/2/4/8/16/32 (set MS pins on driver) |
| `speed_rpm` | float | `10.0` | Initial speed in RPM |
| `auto_enable` | bool | `true` | Energise motor on node startup |
| `gpio_chip` | int | `0` | lgpio chip index (always 0 on Pi 5) |

---

## Topic / Message Contract Summary

| Topic | Direction | Type | Description |
|-------|-----------|------|-------------|
| `/singulation/part_ready` | Pub | `std_msgs/String` (JSON) | Part entered inspection zone |
| `/singulation/motor_N/status` | Pub | `std_msgs/String` (JSON) | Motor state at 1 Hz |
| `/singulation/motor_N/set_speed` | Sub | `std_msgs/Float64` | Change speed (RPM) |
| `/singulation/motor_N/set_enable` | Sub | `std_msgs/Bool` | Enable/disable coils |
| `/singulation/motor_N/set_direction` | Sub | `std_msgs/Bool` | CW=true, CCW=false |

> When `lego_sorter_msgs` is built, `/singulation/part_ready` upgrades from
> `std_msgs/String` JSON to `lego_sorter_msgs/PartReady` — no structural
> changes to the node required, only the publisher type swap.

---

## GitHub Setup — ChaosBuster Account

### First-time setup (on Pi 5 or dev machine)

```bash
# Configure git identity
git config --global user.name  "ChaosBuster"
git config --global user.email "your@email.com"

# Generate SSH key if you don't have one
ssh-keygen -t ed25519 -C "your@email.com"
cat ~/.ssh/id_ed25519.pub
# → paste this into GitHub → Settings → SSH and GPG keys → New SSH key
```

### Create repo and push

```bash
cd ~/ros2_ws/src/lego_sorter_ros2   # or wherever you cloned/created the repo

git init
git add .
git commit -m "feat: initial singulation_controller with 3-motor stepper nodes"

# Create repo on GitHub first (github.com/new), then:
git remote add origin git@github.com:ChaosBuster/lego_sorter_ros2.git
git branch -M main
git push -u origin main
```

### Subsequent commits

```bash
git add -A
git commit -m "your message"
git push
```

---

## Troubleshooting

**Motor doesn't move / makes no sound**
- Check VMOT voltage (must be 8–35 V for A4988, 8–45 V for DRV8825)
- Measure continuity on motor wires — confirm coil pairs
- Verify ENABLE pin is LOW (use multimeter: GPIO 22 should read < 0.5 V when enabled)
- Try `speed_rpm:=1.0` — at very low RPM you can count individual steps by feel

**`lgpio` permission denied**
```bash
sudo usermod -aG gpio $USER && newgrp gpio
# or run with sudo temporarily to confirm it's a permissions issue
```

**`colcon build` fails on lego_sorter_msgs**
```bash
sudo apt install -y ros-jazzy-rosidl-default-generators ros-jazzy-rosidl-default-runtime
source /opt/ros/jazzy/setup.bash
colcon build --packages-select lego_sorter_msgs --cmake-clean-cache
```

**Motor runs but misses steps / stalls**
- Lower `speed_rpm` — NEMA17 torque drops sharply above ~300–600 RPM with no load microstepping
- Verify current limit Vref isn't set too low
- Add a 100 µF cap across VMOT/GND if not already present

---

## Next Steps in the Pipeline

Once motors spin reliably:

1. **Add breakbeam sensors** → implement `breakbeam_tracker` node publishing `/tracking/part_zone` and `/singulation/part_ready` with real `part_id`s
2. **Camera** → `camera_ros` node (`ros-jazzy-v4l2-camera` or PiCamera2 ROS wrapper)
3. **Brickognize** → `brickognize_recognizer` calling the REST API, publishing `/recognition/result`
4. **Routing** → `bin_router` + `diverter_controller`
5. **Upgrade messages** → swap `std_msgs/String` JSON to `lego_sorter_msgs/*` typed messages

The topic contract (`/singulation/part_ready`, `part_id`, zone-based tracking) is already in place — the rest of the pipeline slots in without refactoring this package.
