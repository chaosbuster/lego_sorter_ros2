"""
singulation_all.launch.py

Launches all three NEMA17 stepper motor nodes for the singulation stage.

Each motor instance is independently named and has its own GPIO pin set,
so you can run ros2 launch singulation_controller singulation_all.launch.py
and all three rotors spin up immediately.

For a single motor (e.g. during initial bring-up / wiring testing):
  ros2 launch singulation_controller singulation_all.launch.py

For one motor only:
  ros2 run singulation_controller stepper_node \
      --ros-args \
      -p motor_name:=motor_1 \
      -p step_pin:=17 \
      -p dir_pin:=27 \
      -p enable_pin:=22 \
      -p speed_rpm:=10.0

GPIO pin assignments (default — edit to match your wiring):
  Motor 1 (bottom rotor):   STEP=17, DIR=27, EN=22
  Motor 2 (middle rotor):   STEP=23, DIR=24, EN=25
  Motor 3 (top rotor):      STEP=5,  DIR=6,  EN=13

Aligns with the pipeline's "feeder_controller" role:
  Publishes → /singulation/part_ready
  Status    → /singulation/motor_N/status
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    # ------------------------------------------------------------------
    # Launch arguments — override from CLI or a parent launch file
    # ------------------------------------------------------------------
    args = [
        # Global speed (individual motors can still be overridden via /set_speed)
        DeclareLaunchArgument("speed_rpm",      default_value="10.0",
                              description="Initial motor speed in RPM"),
        DeclareLaunchArgument("microstepping",  default_value="1",
                              description="Microstepping divisor (1/2/4/8/16/32)"),
        DeclareLaunchArgument("steps_per_rev",  default_value="200",
                              description="Full steps per revolution"),
        DeclareLaunchArgument("auto_enable",    default_value="true",
                              description="Enable motors on startup"),
    ]

    speed       = LaunchConfiguration("speed_rpm")
    microstep   = LaunchConfiguration("microstepping")
    spr         = LaunchConfiguration("steps_per_rev")
    auto_en     = LaunchConfiguration("auto_enable")

    # ------------------------------------------------------------------
    # Helper: build a Node for one stepper
    # ------------------------------------------------------------------
    def stepper_node(name, step_pin, dir_pin, enable_pin):
        return Node(
            package="singulation_controller",
            executable="stepper_node",
            name=f"stepper_{name}",
            namespace="singulation",
            output="screen",
            parameters=[{
                "motor_name":    name,
                "step_pin":      step_pin,
                "dir_pin":       dir_pin,
                "enable_pin":    enable_pin,
                "steps_per_rev": spr,
                "microstepping": microstep,
                "speed_rpm":     speed,
                "auto_enable":   auto_en,
                "gpio_chip":     0,         # lgpio chip 0 on Pi 5
            }],
            # Emit structured logs
            emulate_tty=True,
        )

    # ------------------------------------------------------------------
    # Motor node definitions
    # Adjust pin numbers here if your wiring differs
    # ------------------------------------------------------------------
    motor_nodes = [
        stepper_node("motor_1", step_pin=17, dir_pin=27, enable_pin=22),
        stepper_node("motor_2", step_pin=23, dir_pin=24, enable_pin=25),
        stepper_node("motor_3", step_pin=5,  dir_pin=6,  enable_pin=13),
    ]

    return LaunchDescription(args + motor_nodes)
