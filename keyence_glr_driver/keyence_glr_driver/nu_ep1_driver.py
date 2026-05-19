"""Keyence GL-R driver — reads the NU-EP1 input assembly over EtherNet/IP
explicit messaging and publishes CurtainStatus.

The exact assembly instance ID, size, and byte layout come from the NU-EP1
EDS / setup software. Defaults below match the most common "beam monitor"
configuration for a 64-beam GL-R, but verify against your unit.
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles

from keyence_glr_msgs.msg import BeamStatus, CurtainStatus

try:
    from pycomm3 import CIPDriver, Services
    _HAVE_PYCOMM3 = True
except ImportError:
    _HAVE_PYCOMM3 = False


@dataclass
class AssemblyLayout:
    """Byte offsets into the NU-EP1 input assembly. Adjust to match your EDS."""
    status_word_offset: int = 0     # 2 bytes: OSSD A/B, lockout, muted bits
    beam_bitmap_offset: int = 2     # N bytes: 1 bit per beam, LSB = beam 0
    beam_bitmap_bytes: int = 8      # 8 bytes = 64 beams
    blocked_count_offset: int = 10  # 2 bytes: unsigned blocked-beam count


# Bit positions within the status word (little-endian).
STATUS_OSSD_A = 1 << 0
STATUS_OSSD_B = 1 << 1
STATUS_LOCKOUT = 1 << 2
STATUS_MUTED = 1 << 3


class NuEp1Driver(Node):
    def __init__(self) -> None:
        super().__init__('keyence_glr_driver')

        self.declare_parameter('ip_address', '192.168.0.10')
        self.declare_parameter('assembly_instance', 100)
        self.declare_parameter('assembly_size', 12)
        self.declare_parameter('beam_count', 64)
        self.declare_parameter('poll_hz', 20.0)
        self.declare_parameter('frame_id', 'gl_r')
        self.declare_parameter('stale_timeout_s', 0.5)

        self.ip = self.get_parameter('ip_address').value
        self.instance = int(self.get_parameter('assembly_instance').value)
        self.size = int(self.get_parameter('assembly_size').value)
        self.beam_count = int(self.get_parameter('beam_count').value)
        self.frame_id = self.get_parameter('frame_id').value
        self.stale_timeout = float(self.get_parameter('stale_timeout_s').value)
        poll_hz = float(self.get_parameter('poll_hz').value)

        self.layout = AssemblyLayout(beam_bitmap_bytes=(self.beam_count + 7) // 8)

        self.pub = self.create_publisher(
            CurtainStatus, 'gl_r/status', QoSPresetProfiles.SENSOR_DATA.value
        )

        if not _HAVE_PYCOMM3:
            self.get_logger().fatal(
                'pycomm3 not installed. On the Jetson: pip install pycomm3'
            )
            raise SystemExit(1)

        self.driver: CIPDriver | None = None
        self.last_success_t = 0.0

        self.timer = self.create_timer(1.0 / poll_hz, self._tick)
        self.get_logger().info(
            f'Polling NU-EP1 at {self.ip}, assembly={self.instance}, '
            f'size={self.size} B, beams={self.beam_count}, {poll_hz} Hz'
        )

    def _ensure_open(self) -> bool:
        if self.driver is not None:
            return True
        try:
            self.driver = CIPDriver(self.ip)
            self.driver.open()
            return True
        except Exception as exc:
            self.get_logger().warn(f'CIP open failed: {exc}')
            self.driver = None
            return False

    def _read_assembly(self) -> bytes | None:
        if not self._ensure_open():
            return None
        try:
            result = self.driver.generic_message(
                service=Services.get_attribute_single,
                class_code=0x04,           # Assembly object
                instance=self.instance,
                attribute=3,               # Data
                data_format=None,
                connected=False,
                unconnected_send=True,
                route_path=True,
                name='read_input_assembly',
            )
            if not result or not result.value:
                return None
            return bytes(result.value)[: self.size]
        except Exception as exc:
            self.get_logger().warn(f'CIP read failed: {exc}; will reconnect')
            try:
                self.driver.close()
            except Exception:
                pass
            self.driver = None
            return None

    def _tick(self) -> None:
        raw = self._read_assembly()
        now = self.get_clock().now().to_msg()
        msg = CurtainStatus()
        msg.header.stamp = now
        msg.header.frame_id = self.frame_id
        msg.beam_count = self.beam_count

        if raw is None or len(raw) < self.size:
            stale = (time.monotonic() - self.last_success_t) > self.stale_timeout
            msg.beams = [
                BeamStatus(
                    index=i,
                    blocked=False,
                    health=BeamStatus.HEALTH_STALE if stale else BeamStatus.HEALTH_FAULT,
                )
                for i in range(self.beam_count)
            ]
            self.pub.publish(msg)
            return

        self.last_success_t = time.monotonic()
        status_word = struct.unpack_from('<H', raw, self.layout.status_word_offset)[0]
        msg.ossd_a = bool(status_word & STATUS_OSSD_A)
        msg.ossd_b = bool(status_word & STATUS_OSSD_B)
        msg.lockout = bool(status_word & STATUS_LOCKOUT)
        msg.muted = bool(status_word & STATUS_MUTED)

        bitmap = raw[
            self.layout.beam_bitmap_offset:
            self.layout.beam_bitmap_offset + self.layout.beam_bitmap_bytes
        ]
        blocked = 0
        beams: list[BeamStatus] = []
        for i in range(self.beam_count):
            byte = bitmap[i // 8] if (i // 8) < len(bitmap) else 0
            is_blocked = bool(byte & (1 << (i % 8)))
            if is_blocked:
                blocked += 1
            beams.append(
                BeamStatus(index=i, blocked=is_blocked, health=BeamStatus.HEALTH_OK)
            )
        msg.beams = beams
        msg.any_blocked = blocked > 0
        msg.blocked_count = blocked
        self.pub.publish(msg)


def main(argv: list[str] | None = None) -> None:
    rclpy.init(args=argv)
    node = NuEp1Driver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.driver is not None:
            try:
                node.driver.close()
            except Exception:
                pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
