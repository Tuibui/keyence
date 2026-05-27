#!/usr/bin/env python3
"""Probe a Keyence GC-1000 / NU-EP1 over EtherNet/IP and dump what an Assembly
instance actually returns — used to find the real assembly_instance / size /
byte-layout for nu_ep1_driver.

It reads `Assembly object (0x04) / instance N / attribute 3` via unconnected
explicit messaging (same call the driver uses), then:
  * hex-dumps the bytes with offsets,
  * lists every bit that is 1 as a global bit index (byte*8 + bit, LSB first),
  * in watch mode, highlights which bytes/bits change between reads.

Wave your hand through the curtain while it runs: the bits that toggle ARE the
beam bitmap, and their global bit index tells you the byte offset to put in
`AssemblyLayout`. (beam 0 at byte offset 2 => global bit 16.)

Stop the ROS driver first (Ctrl-C the launch) so two clients don't poll at once.

Examples:
  ./probe_gc1000.py                       # live-watch instance 100 @ 192.168.0.10
  ./probe_gc1000.py --ip 192.168.0.10 --instance 101
  ./probe_gc1000.py --once                # single read, then exit
  ./probe_gc1000.py --scan 1-200          # find which instances respond
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    from pycomm3 import CIPDriver, Services
except ImportError:
    sys.exit("pycomm3 not installed.  pip3 install --user pycomm3")


# ANSI colours (skipped automatically when output is not a TTY).
class C:
    use = sys.stdout.isatty()
    R = '\033[31m' if use else ''
    G = '\033[32m' if use else ''
    Y = '\033[33m' if use else ''
    DIM = '\033[2m' if use else ''
    OFF = '\033[0m' if use else ''


def read_assembly(drv, class_code, instance, attribute, service='single'):
    """One get_attribute_{single,all}. Returns (bytes_or_None, error_str_or_None).

    Some EtherNet/IP assemblies reject get_attribute_single (0x0E) with
    "Service not supported" but still answer get_attribute_all (0x01); others
    expose data only through cyclic I/O (Class 1) and answer neither.
    """
    svc = Services.get_attribute_all if service == 'all' else Services.get_attribute_single
    kwargs = dict(
        service=svc,
        class_code=class_code,
        instance=instance,
        data_format=None,
        connected=False,
        unconnected_send=True,
        route_path=True,
        name='probe',
    )
    if service != 'all':
        kwargs['attribute'] = attribute
    try:
        r = drv.generic_message(**kwargs)
    except Exception as exc:                       # noqa: BLE001 - diagnostic tool
        return None, f'{type(exc).__name__}: {exc}'
    if not r or r.value is None:
        return None, getattr(r, 'error', None) or 'no data'
    return bytes(r.value), None


def set_bits(data: bytes) -> set[int]:
    """Global indices of every 1 bit, LSB first (byte b, bit i -> b*8 + i)."""
    out = set()
    for b, byte in enumerate(data):
        for i in range(8):
            if byte & (1 << i):
                out.add(b * 8 + i)
    return out


def hexdump(data: bytes, changed: set[int] | None = None) -> str:
    """Hex bytes, 16 per line, changed byte offsets highlighted."""
    changed = changed or set()
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        cells = []
        for j, byte in enumerate(chunk):
            cell = f'{byte:02x}'
            if (off + j) in changed:
                cell = f'{C.Y}{cell}{C.OFF}'
            cells.append(cell)
        lines.append(f'  {C.DIM}{off:3d}{C.OFF}  ' + ' '.join(cells))
    return '\n'.join(lines)


def parse_instances(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            lo, hi = part.split('-', 1)
            out.extend(range(int(lo), int(hi) + 1))
        elif part:
            out.append(int(part))
    return out


def do_scan(drv, args) -> None:
    print(f'== scanning Assembly(0x{args.class_code:02x}) instances on {args.ip} '
          f'(get_attribute_{args.service}) ==')
    hits = 0
    for inst in parse_instances(args.scan):
        data, err = read_assembly(drv, args.class_code, inst, args.attribute, args.service)
        if data is not None:
            hits += 1
            print(f'  {C.G}inst {inst:4d}{C.OFF}: {len(data):3d}B  {data.hex(" ")}')
        elif args.verbose:
            print(f'  {C.DIM}inst {inst:4d}: {err}{C.OFF}')
    print(f'== {hits} instance(s) responded ==')


def do_watch(drv, args) -> None:
    print(f'== {"single read" if args.once else "live watch"} '
          f'Assembly(0x{args.class_code:02x})/inst {args.instance}/attr {args.attribute} '
          f'(get_attribute_{args.service}) on {args.ip} ==')
    if not args.once:
        print(f'{C.DIM}   wave your hand through the curtain; toggled bits = the beam '
              f'bitmap. Ctrl-C to stop.{C.OFF}')
    prev_bytes: bytes | None = None
    prev_bits: set[int] = set()
    while True:
        data, err = read_assembly(drv, args.class_code, args.instance, args.attribute, args.service)
        if data is None:
            print(f'{C.R}read failed: {err}{C.OFF}')
        else:
            changed = {i for i in range(len(data))
                       if prev_bytes is None or i >= len(prev_bytes)
                       or data[i] != prev_bytes[i]}
            bits = set_bits(data)
            print(f'\n[{time.strftime("%H:%M:%S")}] {len(data)} bytes')
            print(hexdump(data, changed if prev_bytes is not None else set()))
            print(f'  bits=1 (global LSB idx): {sorted(bits) if bits else "[]"}')
            if prev_bytes is not None:
                on = sorted(bits - prev_bits)
                off = sorted(prev_bits - bits)
                if on:
                    print(f'  {C.G}+ turned ON : {on}{C.OFF}')
                if off:
                    print(f'  {C.R}- turned OFF: {off}{C.OFF}')
            prev_bytes, prev_bits = data, bits
        if args.once:
            return
        time.sleep(args.interval)


def main() -> None:
    p = argparse.ArgumentParser(
        description='Probe a Keyence GC-1000 / NU-EP1 EtherNet/IP assembly.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('--ip', default='192.168.0.10', help='GC-1000 / NU-EP1 IP (default 192.168.0.10)')
    p.add_argument('--instance', type=int, default=100, help='assembly instance (default 100)')
    p.add_argument('--attribute', type=int, default=3, help='attribute id (default 3 = Data)')
    p.add_argument('--service', choices=['single', 'all'], default='single',
                   help='CIP read service: get_attribute_single (default) or get_attribute_all')
    p.add_argument('--class-code', type=lambda x: int(x, 0), default=0x04,
                   help='CIP class code (default 0x04 = Assembly)')
    p.add_argument('--interval', type=float, default=0.3, help='seconds between reads in watch mode')
    p.add_argument('--once', action='store_true', help='read once and exit')
    p.add_argument('--scan', metavar='RANGE', help='scan instances e.g. "1-200" or "100,101,150"')
    p.add_argument('-v', '--verbose', action='store_true', help='in --scan, also print non-responding instances')
    args = p.parse_args()

    try:
        with CIPDriver(args.ip) as drv:
            if args.scan:
                do_scan(drv, args)
            else:
                do_watch(drv, args)
    except KeyboardInterrupt:
        print('\nstopped.')
    except Exception as exc:                       # noqa: BLE001 - diagnostic tool
        sys.exit(f'{C.R}connection/driver error: {type(exc).__name__}: {exc}{C.OFF}')


if __name__ == '__main__':
    main()
