"""
singulation_single.launch.py

Launch a single stepper node — ideal for initial wiring verification.

Usage:
  ros2 launch singulation_controller singulation_single.launch.py motor_name:=motor_1

All parameters are overridable from the command line.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    args = [
        DeclareLaunchArgument("motor_name",    default_value="motor_1"),
        DeclareLaunchArgument("step_pin",      default_value="17"),
        DeclareLaunchArgument("dir_pin",       default_value="27"),
        DeclareLaunchArgument("enable_pin",    default_value="22"),
        DeclareLaunchArgument("steps_per_rev", default_value="200"),
        DeclareLaunchArgument("microstepping", default_value="1"),
        DeclareLaunchArgument("speed_rpm",     default_value="10.0"),
        DeclareLaunchArgument("auto_enable",   default_value="true"),
        DeclareLaunchArgument("gpio_chip",     default_value="4"),
    ]

    return LaunchDescription(args + [
        Node(
            package="singulation_controller",
            executable="stepper_node",
            name="stepper_single",
            output="screen",
            emulate_tty=True,
            parameters=[{
                "motor_name":    LaunchConfiguration("motor_name"),
                "step_pin":      LaunchConfiguration("step_pin"),
                "dir_pin":       LaunchConfiguration("dir_pin"),
                "enable_pin":    LaunchConfiguration("enable_pin"),
                "steps_per_rev": LaunchConfiguration("steps_per_rev"),
                "microstepping": LaunchConfiguration("microstepping"),
                "speed_rpm":     LaunchConfiguration("speed_rpm"),
                "auto_enable":   LaunchConfiguration("auto_enable"),
                "gpio_chip":     LaunchConfiguration("gpio_chip"),
            }],
        )
    ])
