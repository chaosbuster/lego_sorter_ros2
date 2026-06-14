#!/usr/bin/env python3
"""
stepper_node.py — ROS 2 Jazzy node for NEMA17 stepper motor control
via A4988/DRV8825 driver on Raspberry Pi 5 GPIO.

One instance per motor. Launch with different parameters for each of
the three singulation stage motors.

Pipeline contract (from ROS_Pipeline_suggested_by_ChatGPT.pdf):
  Publishes: /singulation/part_ready  (std_msgs/String carrying JSON with
             part_id and timestamp — upgrades to lego_sorter_msgs/PartReady
             once that package is built)
  Subscribes: /singulation/motor_N/set_speed  (std_msgs/Float64, RPM)
              /singulation/motor_N/set_enable  (std_msgs/Bool)
              /singulation/motor_N/set_direction (std_msgs/Bool, True=CW)
"""

import json
import math
import threading
import time
import uuid

import lgpio

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool, Float64, String


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_ENABLE_ACTIVE_LOW = True   # A4988 and DRV8825 both pull EN LOW to enable


class StepperNode(Node):
    """
    Controls a single NEMA17 stepper motor through an A4988 or DRV8825 driver.

    ROS Parameters (all overridable at launch):
        motor_name      (str)   Logical name, used in topic namespace  [motor_1]
        step_pin        (int)   BCM GPIO pin → STEP on driver          [17]
        dir_pin         (int)   BCM GPIO pin → DIR on driver           [27]
        enable_pin      (int)   BCM GPIO pin → EN on driver            [22]
        steps_per_rev   (int)   Full steps per revolution              [200]
        microstepping   (int)   Microstepping divisor (1/2/4/8/16/32)  [1]
        speed_rpm       (float) Initial speed in RPM                   [10.0]
        auto_enable     (bool)  Enable motor on startup                [True]
        gpio_chip       (int)   lgpio chip index (0 on Pi 5)           [0]

    Subscribed Topics (namespaced by motor_name):
        /singulation/<motor_name>/set_speed     std_msgs/Float64  (RPM)
        /singulation/<motor_name>/set_enable    std_msgs/Bool
        /singulation/<motor_name>/set_direction std_msgs/Bool  (True = CW)

    Published Topics:
        /singulation/part_ready                 std_msgs/String  (JSON)
        /singulation/<motor_name>/status        std_msgs/String  (JSON)
    """

    def __init__(self):
        super().__init__("stepper_node")

        # ------------------------------------------------------------------
        # Declare and read parameters
        # ------------------------------------------------------------------
        self.declare_parameter("motor_name",    "motor_1")
        self.declare_parameter("step_pin",      17)
        self.declare_parameter("dir_pin",       27)
        self.declare_parameter("enable_pin",    22)
        self.declare_parameter("steps_per_rev", 200)
        self.declare_parameter("microstepping", 1)
        self.declare_parameter("speed_rpm",     10.0)
        self.declare_parameter("auto_enable",   True)
        self.declare_parameter("gpio_chip",     0)

        self._motor_name    = self.get_parameter("motor_name").value
        self._step_pin      = self.get_parameter("step_pin").value
        self._dir_pin       = self.get_parameter("dir_pin").value
        self._enable_pin    = self.get_parameter("enable_pin").value
        self._steps_per_rev = self.get_parameter("steps_per_rev").value
        self._microstepping = self.get_parameter("microstepping").value
        self._speed_rpm     = self.get_parameter("speed_rpm").value
        self._gpio_chip_idx = self.get_parameter("gpio_chip").value

        self.get_logger().info(
            f"[{self._motor_name}] Configuring stepper: "
            f"STEP={self._step_pin}, DIR={self._dir_pin}, "
            f"EN={self._enable_pin}, {self._steps_per_rev} steps/rev, "
            f"microstepping=1/{self._microstepping}, "
            f"speed={self._speed_rpm} RPM"
        )

        # ------------------------------------------------------------------
        # GPIO setup via lgpio (Pi 5 compatible)
        # ------------------------------------------------------------------
        try:
            self._chip = lgpio.gpiochip_open(self._gpio_chip_idx)
        except Exception as exc:
            self.get_logger().fatal(f"Cannot open GPIO chip {self._gpio_chip_idx}: {exc}")
            raise

        for pin in (self._step_pin, self._dir_pin, self._enable_pin):
            lgpio.gpio_claim_output(self._chip, pin, 0)

        # ------------------------------------------------------------------
        # Internal state
        # ------------------------------------------------------------------
        self._enabled   = False
        self._direction = True          # True = CW (DIR pin HIGH)
        self._running   = False
        self._step_lock = threading.Lock()

        # Step interval computed from speed
        self._step_interval_s = self._rpm_to_step_interval(self._speed_rpm)

        # Background step thread
        self._step_thread = threading.Thread(
            target=self._step_loop, daemon=True
        )

        # ------------------------------------------------------------------
        # ROS publishers
        # ------------------------------------------------------------------
        ns = f"/singulation/{self._motor_name}"

        self._pub_part_ready = self.create_publisher(
            String, "/singulation/part_ready", 10
        )
        self._pub_status = self.create_publisher(
            String, f"{ns}/status", 10
        )

        # ------------------------------------------------------------------
        # ROS subscribers
        # ------------------------------------------------------------------
        self.create_subscription(
            Float64, f"{ns}/set_speed",
            self._cb_set_speed, 10
        )
        self.create_subscription(
            Bool, f"{ns}/set_enable",
            self._cb_set_enable, 10
        )
        self.create_subscription(
            Bool, f"{ns}/set_direction",
            self._cb_set_direction, 10
        )

        # ------------------------------------------------------------------
        # Status timer (1 Hz)
        # ------------------------------------------------------------------
        self.create_timer(1.0, self._publish_status)

        # ------------------------------------------------------------------
        # Auto-enable and start
        # ------------------------------------------------------------------
        if self.get_parameter("auto_enable").value:
            self._set_enable(True)

        self._running = True
        self._step_thread.start()

        self.get_logger().info(f"[{self._motor_name}] Node ready.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rpm_to_step_interval(self, rpm: float) -> float:
        """Return seconds between STEP pulses for the given RPM."""
        if rpm <= 0:
            return float("inf")
        effective_steps = self._steps_per_rev * self._microstepping
        steps_per_second = (rpm / 60.0) * effective_steps
        return 1.0 / steps_per_second

    def _set_enable(self, enable: bool):
        """Drive the ENABLE pin (active-low on A4988/DRV8825)."""
        self._enabled = enable
        pin_state = 0 if enable else 1   # LOW = enabled
        lgpio.gpio_write(self._chip, self._enable_pin, pin_state)
        self.get_logger().info(
            f"[{self._motor_name}] Motor {'ENABLED' if enable else 'DISABLED'}"
        )

    def _set_direction(self, cw: bool):
        self._direction = cw
        lgpio.gpio_write(self._chip, self._dir_pin, 1 if cw else 0)

    # ------------------------------------------------------------------
    # Step loop (runs in background thread)
    # ------------------------------------------------------------------

    def _step_loop(self):
        """
        Continuously pulses the STEP pin at the configured interval.
        Respects _enabled state and _step_interval_s (updated by callbacks).
        """
        HIGH, LOW = 1, 0
        PULSE_WIDTH_S = 0.000002    # 2 µs — meets A4988 & DRV8825 minimums

        while self._running:
            interval = self._step_interval_s
            if not self._enabled or interval == float("inf"):
                time.sleep(0.01)
                continue

            # Rising edge
            lgpio.gpio_write(self._chip, self._step_pin, HIGH)
            time.sleep(PULSE_WIDTH_S)
            # Falling edge
            lgpio.gpio_write(self._chip, self._step_pin, LOW)

            # Wait remainder of step interval
            remaining = interval - PULSE_WIDTH_S
            if remaining > 0:
                time.sleep(remaining)

    # ------------------------------------------------------------------
    # ROS callbacks
    # ------------------------------------------------------------------

    def _cb_set_speed(self, msg: Float64):
        rpm = msg.data
        if rpm < 0:
            self.get_logger().warning(
                f"[{self._motor_name}] Negative RPM ignored ({rpm})"
            )
            return
        self._speed_rpm = rpm
        self._step_interval_s = self._rpm_to_step_interval(rpm)
        self.get_logger().info(
            f"[{self._motor_name}] Speed set to {rpm:.2f} RPM "
            f"(step interval {self._step_interval_s*1000:.3f} ms)"
        )

    def _cb_set_enable(self, msg: Bool):
        self._set_enable(msg.data)

    def _cb_set_direction(self, msg: Bool):
        self._set_direction(msg.data)

    # ------------------------------------------------------------------
    # Status publisher
    # ------------------------------------------------------------------

    def _publish_status(self):
        payload = {
            "motor_name":     self._motor_name,
            "enabled":        self._enabled,
            "direction_cw":   self._direction,
            "speed_rpm":      self._speed_rpm,
            "step_pin":       self._step_pin,
            "dir_pin":        self._dir_pin,
            "enable_pin":     self._enable_pin,
            "microstepping":  self._microstepping,
            "steps_per_rev":  self._steps_per_rev,
            "timestamp":      time.time(),
        }
        msg = String()
        msg.data = json.dumps(payload)
        self._pub_status.publish(msg)

    # ------------------------------------------------------------------
    # Part-ready event helper (called by breakbeam_tracker in full pipeline)
    # ------------------------------------------------------------------
    # NOTE: In the minimum viable network, breakbeam_tracker publishes
    #       /singulation/part_ready.  This helper is here so singulation_controller
    #       can also emit synthetic part_ready events during testing
    #       (e.g. timed pulses to simulate part cadence).

    def emit_part_ready(self, zone: str = "inspection"):
        """
        Publish a /singulation/part_ready event in JSON matching the
        PartReady.msg contract (uint64 part_id, Time stamp, string zone,
        float32 conveyor_speed) from the pipeline doc.
        """
        payload = {
            "part_id":        str(uuid.uuid4().int >> 64),   # 64-bit unique ID
            "stamp":          time.time(),
            "zone":           zone,
            "conveyor_speed": self._speed_rpm,
            "source":         self._motor_name,
        }
        msg = String()
        msg.data = json.dumps(payload)
        self._pub_part_ready.publish(msg)
        self.get_logger().debug(
            f"[{self._motor_name}] Emitted part_ready: {payload['part_id']}"
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def destroy_node(self):
        """Clean GPIO state on exit — disable motor, release chip."""
        self.get_logger().info(f"[{self._motor_name}] Shutting down — disabling motor.")
        self._running = False
        if self._step_thread.is_alive():
            self._step_thread.join(timeout=1.0)
        try:
            self._set_enable(False)
            for pin in (self._step_pin, self._dir_pin, self._enable_pin):
                lgpio.gpio_write(self._chip, pin, 0)
            lgpio.gpiochip_close(self._chip)
        except Exception as exc:
            self.get_logger().error(f"GPIO cleanup error: {exc}")
        super().destroy_node()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = StepperNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        if node:
            node.get_logger().fatal(f"Unhandled exception: {exc}")
        raise
    finally:
        if node:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
