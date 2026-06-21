## Terminal 1 — Launch all three motors

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros_sorter/install/setup.bash

ros2 launch singulation_controller singulation_all.launch.py speed_rpm:=25.0
```

Leave this running. It stays in the foreground and streams logs from all three motors. Press `Ctrl+C` here when you want to shut everything down (motors disable cleanly).

---

## Terminal 2 — Open a new terminal/SSH session, send commands

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros_sorter/install/setup.bash
```

**Check what's running:**
```bash
ros2 node list
ros2 topic list | grep singulation
```

**Change a motor's speed:**
```bash
ros2 topic pub --once /singulation/motor_1/set_speed std_msgs/msg/Float64 "data: 10.0"
```

**Enable / disable a motor:**
```bash
ros2 topic pub --once /singulation/motor_2/set_enable std_msgs/msg/Bool "data: false"
ros2 topic pub --once /singulation/motor_2/set_enable std_msgs/msg/Bool "data: true"
```

**Reverse direction:**
```bash
ros2 topic pub --once /singulation/motor_3/set_direction std_msgs/msg/Bool "data: false"
```

**Watch live status:**
```bash
ros2 topic echo /singulation/motor_1/status
```
(`Ctrl+C` just stops watching — doesn't affect the motor.)

---

That's the pattern for the rest of this project too — Terminal 1 runs whatever launch file is active, Terminal 2 (and 3, 4...) are for inspection and control while it's running.
