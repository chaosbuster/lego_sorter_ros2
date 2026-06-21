# LEGO Sorter V2 — ROS 2 Jazzy on Raspberry Pi 5

> **Hardware:** [Basically LEGO Sorter V2](https://basically.website/sorter-v2) — three-stage
> singulation carousel, each stage driven by a NEMA17 42-40 stepper motor via TB6600 driver.
> **Platform:** Raspberry Pi 5, ROS 2 Jazzy, Python, `lgpio`.
> **Status:** ✅ All three motors confirmed spinning independently and simultaneously.

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
> ⚠️ **Do not connect Pi 5V or 12V/24V to the TB6600 signal terminals — logic side is 3.3V only.**

---

### TB6600 Terminal Layout

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

GPIO <step_pin>  ──────────────→ PUL-   (STEP)
GPIO <dir_pin>   ──────────────→ DIR-   (DIRECTION)
GPIO <enable_pin>──────────────→ ENA-   (ENABLE)
```

> **Why common-anode?** The TB6600 uses optocouplers on its inputs. Tying the + side to 3.3V
> and switching the - side LOW with GPIO gives clean, noise-immune signalling.

> ⚠️ **Enable pin is required.** Without ENA wired, the TB6600 stays permanently energized
> regardless of what the software does — `set_enable` calls will have no effect and the
> motor will not be controllable in software. Wire ENA+ → 3.3V and ENA- → your enable_pin
> on every motor.

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

If the motor only oscillates between two positions instead of rotating continuously, this is
almost always a coil-pairing mistake (wires from two different coils mixed into one driver
terminal pair) — re-verify with the multimeter before checking anything else.

If the motor runs in the wrong direction, swap A+ and A- (reverses one coil).

---

### ⚠️ Critical: GPIO Chip Index on Raspberry Pi 5

The Pi 5 exposes **multiple GPIO chips**, and the 40-pin header is **not** on chip 0.

```bash
sudo gpiodetect
```

On the Pi 5, the 40-pin header GPIOs (the ones labeled GPIO2 through GPIO27 in `gpioinfo`)
live on **gpiochip4** (the RP1 southbridge). `gpiochip0` is internal — it includes things like
the power button and PCIe control lines, several of which are already claimed by the system.
Using `gpio_chip:=0` will either silently target the wrong physical pin or fail with a
`GPIO busy` error if it happens to collide with a system-reserved line.

**This package defaults `gpio_chip` to `4`.** Don't override it back to `0` unless you've
confirmed your specific Pi/OS image maps the header differently — verify first with:

```bash
sudo gpioinfo | less
# Search for "GPIO14", "GPIO15", etc. — confirm which gpiochipN they appear under
```

Also be aware some header pins are reserved by the kernel for other peripherals even though
they're physically on the header:

| BCM GPIO | Reserved By | Avoid For Stepper Use |
|----------|-------------|------------------------|
| 2, 3 | I2C | Yes |
| 7, 8 | SPI0 CS1 / CS0 | Yes |
| 9, 10, 11 | SPI0 MISO/MOSI/SCLK | Yes |
| 14, 15 | UART (if enabled) | Only if serial console is active |

Run `sudo gpioinfo` and confirm a candidate pin shows `unused` before wiring to it — pins
marked `[used]` are claimed by the kernel and will throw `GPIO busy` errors.

---

### Confirmed Pin Assignments — This Build

These are the wiring and `gpio_chip` settings verified working on this project's hardware.
Edit `config/motors.yaml` or override at launch if your own wiring differs.

| Motor | Role | STEP (BCM) | DIR (BCM) | ENABLE (BCM) | GPIO Chip |
|-------|------|-----------|-----------|---------------|-----------|
| motor_1 | Bottom rotor | **14** | **15** | **18** | **4** |
| motor_2 | Middle rotor | **23** | **24** | **25** | **4** |
| motor_3 | Top rotor    | **12** | **16** | **20** | **4** |

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

To sanity-check the install:
```bash
sudo apt install -y ros-jazzy-demo-nodes-py ros-jazzy-demo-nodes-cpp
# terminal 1:
ros2 run demo_nodes_py talker
# terminal 2:
ros2 run demo_nodes_py listener
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

> **Note:** On Ubuntu 24.04 the correct apt package is `python3-lgpio` — the bare `lgpio`
> package does not exist in the repos.

### 4. GPIO group (optional — lets you skip `sudo`)

Ubuntu does not create a `gpio` group by default the way Raspberry Pi OS does.

```bash
sudo groupadd gpio
sudo usermod -aG gpio $USER
echo 'SUBSYSTEM=="gpio", GROUP="gpio", MODE="0660"' | sudo tee /etc/udev/rules.d/99-gpio.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo reboot
```

After reboot, confirm:
```bash
groups $USER
# should list "gpio"
```

> **Important:** If you run nodes with `sudo` instead of setting up this group, remember that
> `sudo` does **not** inherit your shell's sourced ROS environment or `PATH`. Either set up the
> group (recommended) or use `sudo -E env "PATH=$PATH" ros2 ...` for every command.

### 5. Clone and build

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

> **Tip:** If colcon picks up a virtualenv Python instead of the system Python (look for a
> `.venv` path in any error mentioning `ModuleNotFoundError: No module named 'em'` or
> `'ament_package'`), force the system interpreter:
> ```bash
> rm -rf build/ install/ log/
> COLCON_PYTHON_EXECUTABLE=/usr/bin/python3 colcon build --packages-select lego_sorter_msgs
> ```
> Make it permanent with `echo "export COLCON_PYTHON_EXECUTABLE=/usr/bin/python3" >> ~/.bashrc`.

### 6. Verify install

```bash
ros2 pkg list | grep -E "lego_sorter|singulation"
# Expected:
# lego_sorter_msgs
# singulation_controller
```

---

## Running the Nodes

ROS 2 launch commands run in the foreground and block the terminal. Use **two terminals**:
one to launch, one to send commands and inspect state.

### Terminal 1 — Single motor test (first bring-up)

Wire one motor, then:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros_sorter/install/setup.bash

ros2 launch singulation_controller singulation_single.launch.py \
    motor_name:=motor_1 \
    step_pin:=14 \
    dir_pin:=15 \
    enable_pin:=18 \
    speed_rpm:=5.0 \
    gpio_chip:=4
```

You should hear the motor stepping continuously. If it only oscillates between two positions,
recheck coil pairing with a multimeter — that symptom is almost never a software issue.

### Terminal 1 — All three motors

```bash
ros2 launch singulation_controller singulation_all.launch.py speed_rpm:=25.0
```

Pin assignments for all three motors are baked into `singulation_all.launch.py` — see the
Confirmed Pin Assignments table above. Edit that file if your wiring differs.

Leave this running. Press `Ctrl+C` to shut down — each motor's enable pin should drop and
you'll see `Shutting down — disabling motor` for each.

### Terminal 2 — Inspect and control while running

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros_sorter/install/setup.bash

ros2 node list
# /singulation/stepper_motor_1
# /singulation/stepper_motor_2
# /singulation/stepper_motor_3

ros2 topic list | grep singulation
```

---

## Runtime Control via ROS Topics

All topics are namespaced per motor: `/singulation/motor_N/...`

### Change speed (RPM) at runtime

```bash
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
ros2 topic echo /singulation/motor_1/status
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
| `gpio_chip` | int | `4` | lgpio chip index — **4** for the Pi 5 header (RP1), not 0 |

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

**`GPIO busy` error on launch**
- You're very likely targeting `gpio_chip:=0` instead of `4`, or the specific pin is reserved
  by the kernel (SPI/I2C/UART). Run `sudo gpioinfo` and confirm the pin shows `unused` on
  `gpiochip4` before using it.

**Motor doesn't move or make sound**
- Verify PSU voltage reaches TB6600 VCC terminal (measure with multimeter)
- Confirm DIP switches match intended current and microstepping settings
- Check PUL- is connected to the correct GPIO (not PUL+)
- Try `speed_rpm:=2.0` — at very low RPM you can feel each individual step

**Motor toggles between two positions instead of rotating**
- This is a coil-pairing problem, not software. Disconnect the motor and re-verify with a
  multimeter which wire pairs belong to which coil (~3–5 Ω = same coil, ∞ = different coils).
  A wire from one coil mixed into the other coil's terminal pair causes exactly this symptom.

**Motor stays energized no matter what software does**
- The ENABLE pin is likely not wired. Confirm ENA+ → 3.3V and ENA- → your `enable_pin` GPIO.
  Without it, the TB6600 defaults to always-enabled and `set_enable` calls have no effect.

**`lgpio` permission denied**
```bash
sudo groupadd gpio
sudo usermod -aG gpio $USER
echo 'SUBSYSTEM=="gpio", GROUP="gpio", MODE="0660"' | sudo tee /etc/udev/rules.d/99-gpio.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
# Or simply run with: sudo -E env "PATH=$PATH" ros2 launch ...
```

**`sudo: ros2: command not found`**
- `sudo` doesn't inherit your shell's `PATH`. Either avoid `sudo` by setting up the `gpio`
  group above, or run `sudo -E env "PATH=$PATH" ros2 ...`.

**`colcon build` picks up wrong Python / virtualenv**
```bash
rm -rf build/ install/ log/
COLCON_PYTHON_EXECUTABLE=/usr/bin/python3 colcon build --packages-select lego_sorter_msgs
echo "export COLCON_PYTHON_EXECUTABLE=/usr/bin/python3" >> ~/.bashrc
```

**`colcon build` fails on lego_sorter_msgs**
```bash
sudo apt install -y ros-jazzy-rosidl-default-generators ros-jazzy-rosidl-default-runtime
source /opt/ros/jazzy/setup.bash
rm -rf ~/ros_sorter/build ~/ros_sorter/install
COLCON_PYTHON_EXECUTABLE=/usr/bin/python3 colcon build --packages-select lego_sorter_msgs
```

**Launch file fails with `IndentationError` / `InvalidFrontendLaunchFileError`**
- A manual edit (often via `nano`) introduced mixed tabs/spaces or a stray indent. Validate
  before relaunching:
  ```bash
  python3 -m py_compile path/to/file.launch.py && echo "Syntax OK"
  ```

**Motor runs backwards**
- Swap A+ and A- at the TB6600 motor terminals, or
- Send `ros2 topic pub --once /singulation/motor_1/set_direction std_msgs/msg/Bool "data: false"`

**Motor stalls or misses steps**
- Lower `speed_rpm` — NEMA17 torque drops sharply above ~300 RPM at full step
- Increase current limit one step on the TB6600 DIP switches (check motor temperature after 5 min)
- Increase microstepping for smoother motion; update the `microstepping` parameter to match

---

## Next Steps in the Pipeline

Once motors spin reliably:

1. **Breakbeam sensors** → implement `breakbeam_tracker` node publishing `/tracking/part_zone` and `/singulation/part_ready` with real `part_id`s
2. **Camera** → `camera_ros` node (`ros-jazzy-v4l2-camera` or PiCamera2 ROS wrapper)
3. **Brickognize** → `brickognize_recognizer` calling the REST API, publishing `/recognition/result`
4. **Routing** → `bin_router` + `diverter_controller`
5. **Upgrade messages** → swap `std_msgs/String` JSON to typed `lego_sorter_msgs/*` messages

The topic contracts (`/singulation/part_ready`, `part_id`, zone-based tracking) are already in place — the rest of the pipeline slots in without refactoring this package.
