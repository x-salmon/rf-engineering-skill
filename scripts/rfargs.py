"""Shared argument parsers: SI-suffixed quantities, distances, complex impedances."""
import argparse
import re

_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0,
           "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}
_LENGTH = {"km": 1e3, "m": 1.0, "cm": 1e-2, "mm": 1e-3, "mi": 1609.344, "nmi": 1852.0,
           "ft": 0.3048, "in": 0.0254}


def qty(text, base_unit=""):
    """Parse '2.4GHz' -> 2.4e9. base_unit is the SI unit to strip (Hz, H, F, s)."""
    s = str(text).strip().replace(" ", "")
    if base_unit and s.lower().endswith(base_unit.lower()):
        s = s[: -len(base_unit)]
    # prefixes are case-sensitive (m = milli, M = mega), so no re.I here
    m = re.fullmatch(r"([-+]?[\d.]+(?:[eE][-+]?\d+)?)([pnuµmkKMGT]?)", s)
    if not m:
        raise argparse.ArgumentTypeError(f"cannot parse '{text}' as {base_unit or 'number'}")
    return float(m.group(1)) * _PREFIX[m.group(2)]


def freq(text):
    return qty(text, "Hz")


def dist(text):
    s = str(text).strip().replace(" ", "")
    m = re.fullmatch(r"([-+]?[\d.]+(?:e[-+]?\d+)?)(km|nmi|mi|cm|mm|m|ft|in)?", s)
    if not m:
        raise argparse.ArgumentTypeError(f"cannot parse distance '{text}'")
    return float(m.group(1)) * _LENGTH[m.group(2) or "m"]


def cplx(text):
    return complex(str(text).replace(" ", "").replace("i", "j"))
