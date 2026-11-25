#!/usr/bin/env python3
"""Talk to bench instruments over VISA (LAN/USB/GPIB): spectrum analyzers, sig gens, VNAs.

Read-only by default. Anything that changes instrument state needs --allow-write, because
a wrong command can key a generator into a live antenna or wipe a saved setup.

  instrument.py list
  instrument.py idn  TCPIP0::192.168.1.50::INSTR
  instrument.py query TCPIP0::192.168.1.50::INSTR ":FREQ:CENT?"
  instrument.py peak TCPIP0::192.168.1.50::INSTR            marker-to-peak, read X/Y
  instrument.py write TCPIP0::... ":FREQ:CENT 121.5MHZ" --allow-write
  instrument.py trace TCPIP0::... --csv trace.csv           pull trace 1 as CSV

Needs: pip install pyvisa pyvisa-py  (or NI-VISA / Keysight IO Libraries installed).
SCPI dialects differ; see references/instruments.md for vendor command tables.
"""
import argparse
import csv
import sys

TIMEOUT_MS = 10_000


def _rm():
    try:
        import pyvisa
    except ImportError:
        sys.exit("pyvisa missing: pip install pyvisa pyvisa-py")
    try:
        return pyvisa.ResourceManager()
    except (OSError, ValueError):
        return pyvisa.ResourceManager("@py")


def _open(resource):
    inst = _rm().open_resource(resource)
    inst.timeout = TIMEOUT_MS
    return inst


def _check_error(inst):
    try:
        err = inst.query(":SYST:ERR?").strip()
    except Exception as exc:  # instrument may not implement SYST:ERR
        return f"(no SYST:ERR: {exc})"
    return None if err.startswith(("0", "+0")) else err


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["list", "idn", "query", "write", "peak", "trace"])
    ap.add_argument("resource", nargs="?")
    ap.add_argument("command", nargs="?")
    ap.add_argument("--allow-write", action="store_true")
    ap.add_argument("--csv")
    a = ap.parse_args(argv)

    if a.action == "list":
        for r in _rm().list_resources():
            print(r)
        return 0
    if not a.resource:
        ap.error("resource string required")
    inst = _open(a.resource)
    try:
        if a.action == "idn":
            print(inst.query("*IDN?").strip())
        elif a.action == "query":
            if not a.command or not a.command.strip().endswith("?"):
                ap.error("query needs a command ending in '?'")
            print(inst.query(a.command).strip())
        elif a.action == "write":
            if not a.allow_write:
                ap.error("write changes instrument state; re-run with --allow-write")
            inst.write(a.command)
            err = _check_error(inst)
            print(f"sent: {a.command}" + (f"\ninstrument error: {err}" if err else ""))
        elif a.action == "peak":
            if not a.allow_write:
                print("note: marker-to-peak moves marker 1 (harmless); allowed in read mode")
            inst.write(":CALC:MARK1:STAT ON")
            inst.write(":CALC:MARK1:MAX")
            x = float(inst.query(":CALC:MARK1:X?"))
            y = float(inst.query(":CALC:MARK1:Y?"))
            print(f"peak: {x / 1e6:.6f} MHz  {y:.2f} dBm")
        elif a.action == "trace":
            inst.write(":FORM ASC")
            data = [float(v) for v in inst.query(":TRAC? TRACE1").split(",")]
            start = float(inst.query(":FREQ:STAR?"))
            stop = float(inst.query(":FREQ:STOP?"))
            step = (stop - start) / max(len(data) - 1, 1)
            rows = [(start + i * step, v) for i, v in enumerate(data)]
            peak = max(rows, key=lambda r: r[1])
            print(f"{len(rows)} points  {start / 1e6:.3f}-{stop / 1e6:.3f} MHz  "
                  f"peak {peak[1]:.2f} dBm @ {peak[0] / 1e6:.4f} MHz")
            if a.csv:
                with open(a.csv, "w", newline="", encoding="utf-8") as fh:
                    csv.writer(fh).writerows([("freq_hz", "dbm"), *rows])
                print(f"wrote {a.csv}")
    finally:
        inst.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
