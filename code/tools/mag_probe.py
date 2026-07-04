import argparse
import time

import serial


INTERESTING_PREFIXES = (
    "I2C_SCAN",
    "MPU6050",
    "COMPASS",
    "COMPASS_PROBE",
    "COMPASS_ADDR",
    "DUMP",
    "MAG",
    "AIM",
    "MAG_CAL",
    "HEADING_CAL",
    "AIMDEBUG",
    "MODE_OK",
    "MODE_ERR",
    "POKE_OK",
    "CMD?",
)


def read_lines(ser, seconds):
    deadline = time.time() + seconds
    buf = b""
    while time.time() < deadline:
        chunk = ser.read(256)
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("utf-8", "backslashreplace").strip()
            if line and line.startswith(INTERESTING_PREFIXES):
                print(line)


def send(ser, command, settle=0.35):
    print(f">>> {command}")
    ser.write((command + "\n").encode("ascii"))
    read_lines(ser, settle)


def main():
    parser = argparse.ArgumentParser(description="Probe Soupocalypse player magnetometer registers.")
    parser.add_argument("port", nargs="?", default="COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--probe-modes", action="store_true", help="Try HMC/QMC/ALT register modes before the normal ALT mode.")
    parser.add_argument("--cal", action="store_true", help="Recenter heading after selecting the ALT compass mode.")
    parser.add_argument("--cal-delay", type=float, default=0.0, help="Seconds to wait before CAL so you can point the board forward.")
    parser.add_argument("--magcal-ms", type=int, default=0, help="Run flat XY magnetometer calibration for this many ms.")
    parser.add_argument("--watch", type=float, default=0.0, help="Seconds to stream MAGDEBUG output after probing.")
    parser.add_argument("--aim-watch", type=float, default=0.0, help="Seconds to stream compact AIMDEBUG output after probing.")
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.08, write_timeout=0.2) as ser:
        print(f"connected {args.port}")
        read_lines(ser, 2.0)
        send(ser, "SCAN")
        send(ser, "DUMP,0x2C,0x00,0x20")
        send(ser, "MAG")
        if args.probe_modes:
            for mode in ("HMC", "QMC", "ALT"):
                send(ser, f"MODE,{mode}", settle=0.55)
                for _ in range(3):
                    send(ser, "MAG", settle=0.22)
        send(ser, "MODE,ALT", settle=0.4)
        if args.magcal_ms > 0:
            send(ser, f"MAGCAL,{args.magcal_ms}", settle=args.magcal_ms / 1000.0 + 0.8)
        if args.cal:
            if args.cal_delay > 0:
                print(f"waiting {args.cal_delay:.1f}s before CAL")
                read_lines(ser, args.cal_delay)
            send(ser, "CAL", settle=0.4)
        if args.watch > 0:
            send(ser, "MAGDEBUG,1", settle=0.2)
            read_lines(ser, args.watch)
            send(ser, "MAGDEBUG,0", settle=0.2)
        if args.aim_watch > 0:
            send(ser, "AIMDEBUG,1", settle=0.2)
            read_lines(ser, args.aim_watch)
            send(ser, "AIMDEBUG,0", settle=0.2)
        print("done")


if __name__ == "__main__":
    main()
