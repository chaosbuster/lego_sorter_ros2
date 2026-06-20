# LEGO Sorter V2 — ROS 2 Jazzy on Raspberry Pi 5

> **Hardware:** [Basically LEGO Sorter V2](https://basically.website/sorter-v2) — three-stage
> singulation carousel, each stage driven by a NEMA17 42-40 stepper motor via TB6600 driver.
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

## Hardware: Wiring TB6600 → Pi 5 GPIO → NEMA17

### Bill of Materials (per motor)

| Qty | Part |
|-----|------|
| 1 | NEMA17 42-40 stepper motor |
| 1 | TB6600 stepper driver |
| 1 | 12V–24V DC power supply (rated ≥ 3A) |
| — | Jumper wires (signal side) |
| — | Ferrule-terminated wire (motor + power side) |

> ⚠️ **Never connect or disconnect the motor while the driver is powered.**
> ⚠️ **Do not connect Pi 5V or 12V/24V to the TB6600 signal terminals — logic side is 3.3V–5V only.**

---

### TB6600 Terminal Layout

The TB6600 has two groups of screw terminals — signal on one side, power and motor on the other.

```
       TB6600
  ┌────────────────┐
  │ ENA+  │  VCC  │
  │ ENA-  │  GND  │
  │ DIR+  │  A+   │
  │ DIR-  │  A-   │
  │ PUL+  │  B+   │
  │ PUL-  │  B-   │
  └────────────────┘
  Signal ←→ Power/Motor
```

---

### Wiring: Signal Side (Pi 5 → TB6600)

The TB6600 uses **common-anode** wiring. Connect all + terminals to Pi 3.3V, and the - terminals to the GPIO pins. The GPIO pulls the line LOW to signal.

```
Raspberry Pi 5                    TB6600 Signal Side
──────────────────                ──────────────────
3.3V  (Pin 1)    ────────┬──────→ PUL+
                         ├──────→ DIR+
                         └──────→ ENA+

GPIO 17 (Pin 11) ──────────────→ PUL-   (STEP)
GPIO 27 (Pin 13) ──────────────→ DIR-   (DIRECTION)
GPIO 22 (Pin 15) ──────────────→ ENA-   (ENABLE)

GND   (Pin 6)    ──────────────→ (not connected on signal side)
```

> **Why common-anode?** The TB6600 uses optocouplers on its inputs. Tying the + side to 3.3V
> and switching the - side LOW with GPIO gives clean, noise-immune signalling.

---

### Wiring: Power Side (PSU → TB6600)

```
12V–24V PSU                       TB6600 Power Side
───────────────                   ─────────────────
PSU  +  ──────────────────────→  VCC
PSU  -  ──────────────────────→  GND
```

> **Voltage choice:** 12V works fine for initial testing. 24V gives more torque and
> smoother high-speed operation. The TB6600 accepts 9V–42V.

---

### Wiring: Motor Side (TB6600 → NEMA17)

```
TB6600 Motor Side                 NEMA17
─────────────────                 ──────
A+  ──────────────────────────→  Coil A wire 1
A-  ──────────────────────────→  Coil A wire 2
B+  ──────────────────────────→  Coil B wire 1
B-  ──────────────────────────→  Coil B wire 2
```

#### Identifying NEMA17 coil pairs with a multimeter

Set multimeter to resistance (Ω). Probe pairs of wires:
- Two wires showing ~3–5 Ω continuity → same coil
- Two wires showing no continuity (∞) → different coils

```
Common wire colours (not universal — always verify with multimeter):
  Coil A: Red  / Green
  Coil B: Blue / Yellow  (or Black / White)
```

If the motor runs in the wrong direction, swap A+ and A- (reverses one coil).

---

### Raspberry Pi 5 GPIO Header — Pin Reference

```
Pi 5 Header (relevant pins only)

 [Pin 1 ]  3.3V  ──→ PUL+ / DIR+ / ENA+ (all three + terminals)
 [Pin 6 ]  GND   ──→ (logic ground reference, connect if needed)
 [Pin 11]  GPIO17 ──→ PUL-  (STEP)
 [Pin 13]  GPIO27 ──→ DIR-  (DIRECTION)
 [Pin 15]  GPIO22 ──→ ENA-  (ENABLE)
```

---

### TB6600 DIP Switch Settings

The TB6600 has 6 DIP switches on the side — SW1–SW3 set current, SW4–SW6 set microstepping.

#### Current Limit (SW1–SW3)

The NEMA17 42-40 is typically rated 1.5–1.7 A/phase. Start at 1.5A.

| SW1 | SW2 | SW3 | Peak Current |
|-----|-----|-----|-------------|
| ON  | ON  | ON  | 0.5A |
| ON  | ON  | OFF | 1.0A |
| ON  | OFF | ON  | 1.5A ← **recommended start** |
| ON  | OFF | OFF | 2.0A |
| OFF | ON  | ON  | 2.5A |
| OFF | ON  | OFF | 2.8A (max for NEMA17) |

#### Microstepping (SW4–SW6)

| SW4 | SW5 | SW6 | Microstep |
|-----|-----|-----|-----------|
| ON  | ON  | ON  | Full step (1) ← **start here** |
| ON  | ON  | OFF | Half step (2) |
| ON  | OFF | ON  | 4 |
| ON  | OFF | OFF | 8 ← good balance of smoothness/speed |
| OFF | ON  | ON  | 16 |
| OFF | ON  | OFF | 32 |

Start with full step for initial wiring verification. Once the motor spins correctly, switch to 8 or 16 for smoother operation and update the `microstepping` ROS parameter to match.

---

### Enable Pin Logic (TB6600 vs A4988)

> **Important:** The TB6600 enable pin logic is the **opposite** of the A4988/DRV8825.

| Driver | ENA HIGH | ENA LOW |
|--------|----------|---------|
| A4988 / DRV8825 | Disabled | **Enabled** |
| **TB6600** | **Enabled** | Disabled |

The `stepper_node.py` is already configured correctly for the TB6600 (`_ENABLE_ACTIVE_LOW = False`).

---

### Pin Assignments for All Three Motors

Edit `config/motors.yaml` or override at launch if your wiring differs.

| Motor | Role | PUL- (STEP) BCM | DIR- (DIR) BCM | ENA- (EN) BCM |
|-------|------|----------------|---------------|--------------|
| motor_1 | Bottom rotor | **17** (Pin 11) | **27** (Pin 13) | **22** (Pin 15) |
| motor_2 | Middle rotor | **23** (Pin 16) | **24** (Pin 18) | **25** (Pin 22) |
| motor_3 | Top rotor    | **5**  (Pin 29) | **6**  (Pin 31) | **13** (Pin 33) |

---

## Software Setup

### 1. OS Prerequisite

Ubuntu 24.04 LTS 64-bit on the Raspberry Pi 5. Download from [ubuntu.com/download/raspberry-pi](https://ubuntu.com/download/raspberry-pi).

After flashing, verify `/etc/apt/sources.list.d/ubuntu.sources` includes `noble-updates noble-backports` on the `Suites:` line — required for ROS 2 binary install.

### 2. Install ROS 2 Jazzy

```bash
sudo apt update && sudo apt install -y curl gnupg lsb-release

sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
    | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y ros-jazzy-ros-base ros-dev-tools

sudo rosdep init && rosdep update

echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

### 3. System dependencies

```bash
sudo apt install -y \
    python3-lgpio \
    ros-jazzy-std-msgs \
    ros-jazzy-launch-ros \
    ros-jazzy-rosidl-default-generators \
    ros-jazzy-rosidl-default-runtime
```

> **Note:** On Ubuntu 24.04 the package is `python3-lgpio` — not `lgpio`.
> The `gpio` group does not exist by default on Ubuntu; create it if needed or run nodes with `sudo`.

### 4. Clone and build

```bash
mkdir -p ~/ros_sorter/src
cd ~/ros_sorter/src
git clone https://github.com/ChaosBuster/lego_sorter_ros2.git

cd ~/ros_sorter
source /opt/ros/jazzy/setup.bash

# Build custom messages first — singulation_controller depends on them
COLCON_PYTHON_EXECUTABLE=/usr/bin/python3 colcon build --packages-select lego_sorter_msgs
COLCON_PYTHON_EXECUTABLE=/usr/bin/python3 colcon build --packages-select singulation_controller

source install/setup.bash
echo "source ~/ros_sorter/install/setup.bash" >> ~/.bashrc
```

> **Tip:** If colcon picks up a virtualenv Python instead of the system Python, prefix every
> `colcon build` with `COLCON_PYTHON_EXECUTABLE=/usr/bin/python3` or add
> `export COLCON_PYTHON_EXECUTABLE=/usr/bin/python3` to `~/.bashrc`.

### 5. Verify install

```bash
ros2 pkg list | grep -E "lego_sorter|singulation"
# Expected output:
# lego_sorter_msgs
# singulation_controller
```

---

## Running the Nodes

### Single motor test (first bring-up)

Wire Motor 1 only, then:

```bash
sudo ros2 launch singulation_controller singulation_single.launch.py \
    motor_name:=motor_1 \
    step_pin:=17 \
    dir_pin:=27 \
    enable_pin:=22 \
    speed_rpm:=5.0
```

You should hear the motor stepping. If not, re-check wiring and DIP switches.

### All three motors

```bash
sudo ros2 launch singulation_controller singulation_all.launch.py speed_rpm:=10.0
```

---

## Runtime Control via ROS Topics

All topics are namespaced per motor: `/singulation/motor_N/...`

### Change speed (RPM) at runtime

```bash
# Set motor_1 to 20 RPM
ros2 topic pub --once /singulation/motor_1/set_speed std_msgs/msg/Float64 "data: 20.0"

# Stop motor_2 (0 RPM — motor stays enabled/holding torque)
ros2 topic pub --once /singulation/motor_2/set_speed std_msgs/msg/Float64 "data: 0.0"
```

### Enable / disable motor

```bash
# Disable (coils de-energised — rotor free to spin by hand)
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
# Live status JSON at 1 Hz
ros2 topic echo /singulation/motor_1/status

# Watch for part-ready events
ros2 topic echo /singulation/part_ready
```

---

## ROS Parameter Reference

All parameters settable at launch via `-p key:=value` or in a YAML override file.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `motor_name` | string | `motor_1` | Logical name; used in topic namespace |
| `step_pin` | int | `17` | BCM GPIO → PUL- on TB6600 |
| `dir_pin` | int | `27` | BCM GPIO → DIR- on TB6600 |
| `enable_pin` | int | `22` | BCM GPIO → ENA- on TB6600 |
| `steps_per_rev` | int | `200` | Full steps per revolution (1.8° NEMA17 = 200) |
| `microstepping` | int | `1` | Must match TB6600 SW4–SW6 DIP setting |
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
> `std_msgs/String` JSON to `lego_sorter_msgs/PartReady` — only the publisher
> type changes, no structural refactoring needed.

---

## GitHub Setup — ChaosBuster Account

### First-time SSH setup (on Pi 5)

```bash
git config --global user.name  "ChaosBuster"
git config --global user.email "your@email.com"

ssh-keygen -t ed25519 -C "your@email.com"
cat ~/.ssh/id_ed25519.pub
# Paste output into: GitHub → Settings → SSH and GPG keys → New SSH key
```

Test the connection:
```bash
ssh -T git@github.com
# Expected: Hi ChaosBuster! You've successfully authenticated...
```

### Subsequent commits

```bash
cd ~/ros_sorter/src/lego_sorter_ros2
git add -A
git commit -m "your message"
git push
```

---

## Troubleshooting

**Motor doesn't move or make sound**
- Verify PSU voltage reaches TB6600 VCC terminal (measure with multimeter)
- Confirm DIP switches match intended current and microstepping settings
- Check PUL- is connected to GPIO 17 (not PUL+)
- Try `speed_rpm:=2.0` — at very low RPM you can feel each individual step

**`lgpio` permission denied**
```bash
sudo groupadd gpio
sudo usermod -aG gpio $USER
echo 'SUBSYSTEM=="gpio", GROUP="gpio", MODE="0660"' | sudo tee /etc/udev/rules.d/99-gpio.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
# Or simply run with: sudo ros2 launch ...
```

**`colcon build` picks up wrong Python / virtualenv**
```bash
# Deactivate any venv, then:
COLCON_PYTHON_EXECUTABLE=/usr/bin/python3 colcon build --packages-select lego_sorter_msgs
# Make permanent:
echo "export COLCON_PYTHON_EXECUTABLE=/usr/bin/python3" >> ~/.bashrc
```

**`colcon build` fails on lego_sorter_msgs**
```bash
sudo apt install -y ros-jazzy-rosidl-default-generators ros-jazzy-rosidl-default-runtime
source /opt/ros/jazzy/setup.bash
rm -rf ~/ros_sorter/build ~/ros_sorter/install
COLCON_PYTHON_EXECUTABLE=/usr/bin/python3 colcon build --packages-select lego_sorter_msgs
```

**Motor runs backwards**
- Swap A+ and A- at the TB6600 motor terminals, or
- Send `ros2 topic pub --once /singulation/motor_1/set_direction std_msgs/msg/Bool "data: false"`

**Motor stalls or misses steps**
- Lower `speed_rpm` — NEMA17 torque drops sharply above ~300 RPM at full step
- Increase current limit one step on SW1–SW3 (check motor temperature after 5 min)
- Increase microstepping for smoother motion; update `microstepping` parameter to match

---

## Next Steps in the Pipeline

Once motors spin reliably:

1. **Breakbeam sensors** → implement `breakbeam_tracker` node publishing `/tracking/part_zone` and `/singulation/part_ready` with real `part_id`s
2. **Camera** → `camera_ros` node (`ros-jazzy-v4l2-camera` or PiCamera2 ROS wrapper)
3. **Brickognize** → `brickognize_recognizer` calling the REST API, publishing `/recognition/result`
4. **Routing** → `bin_router` + `diverter_controller`
5. **Upgrade messages** → swap `std_msgs/String` JSON to typed `lego_sorter_msgs/*` messages

The topic contracts (`/singulation/part_ready`, `part_id`, zone-based tracking) are already in place — the rest of the pipeline slots in without refactoring this package.
