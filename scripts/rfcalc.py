#!/usr/bin/env python3
"""rfcalc - RF engineering calculator. Run `rfcalc.py -h` or `rfcalc.py <cmd> -h`.

Quantities accept SI suffixes: 2.4GHz, 118.5MHz, 25kHz, 10km, 300m, 3mi, 100ft, 10nH, 4.7pF.
Add --json to any command for machine-readable output.
"""
import argparse
import json
import math
import re
import sys

import rfcore as c
import rfprop as p

_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0,
           "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}
_LENGTH = {"km": 1e3, "m": 1.0, "cm": 1e-2, "mm": 1e-3, "mi": 1609.344, "nmi": 1852.0,
           "ft": 0.3048, "in": 0.0254}


def qty(text, base_unit):
    """Parse '2.4GHz' -> 2.4e9. base_unit is the SI unit letter(s) to strip (Hz, H, F)."""
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


def fmt(v):
    if isinstance(v, float):
        if math.isinf(v) or math.isnan(v):
            return str(v)
        a = abs(v)
        if a != 0 and (a < 1e-3 or a >= 1e7):
            return eng(v)
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def eng(v):
    if v == 0:
        return "0"
    exp = int(math.floor(math.log10(abs(v)) / 3) * 3)
    exp = max(-15, min(12, exp))
    sym = {-15: "f", -12: "p", -9: "n", -6: "u", -3: "m", 0: "", 3: "k", 6: "M", 9: "G",
           12: "T"}[exp]
    return f"{v / 10 ** exp:.4g}{sym}"


def show(obj, indent=0):
    pad = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                print(f"{pad}{k}:")
                show(v, indent + 1)
            elif v is not None:
                print(f"{pad}{k}: {fmt(v)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                print(pad + ", ".join(f"{k}={fmt(v)}" for k, v in item.items()))
            else:
                print(pad + fmt(item))


def parse_stages(specs):
    """'gain:nf[:oip3]' per stage, e.g. 20:1.2:30  -3:3  (passive -3 dB)."""
    out = []
    for s in specs:
        parts = [float(x.replace("~", "-")) for x in s.split(":")]
        if len(parts) not in (2, 3):
            raise ValueError(f"stage '{s}' must be gain:nf or gain:nf:oip3")
        out.append({"gain_db": parts[0], "nf_db": parts[1],
                    "oip3_dbm": parts[2] if len(parts) == 3 else None})
    return out


def build_parser():
    ap = argparse.ArgumentParser(prog="rfcalc", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    sp = ap.add_subparsers(dest="cmd", required=True)

    a = sp.add_parser("convert", help="dBm/W/V/uV/dBuV conversions")
    a.add_argument("value", type=float)
    a.add_argument("unit")
    a.add_argument("--z0", type=float, default=50.0)

    a = sp.add_parser("dbsum", help="power-sum several dBm levels")
    a.add_argument("levels", type=float, nargs="+")

    a = sp.add_parser("wavelength", help="wavelength, dipole and vertical cut lengths")
    a.add_argument("f", type=freq)
    a.add_argument("--vf", type=float, default=1.0)

    a = sp.add_parser("fspl", help="free-space path loss")
    a.add_argument("f", type=freq)
    a.add_argument("d", type=dist)

    a = sp.add_parser("link", help="full link budget with margin and SNR")
    a.add_argument("--f", type=freq, required=True)
    a.add_argument("--d", type=dist, required=True)
    a.add_argument("--ptx", type=float, required=True, help="TX power dBm")
    a.add_argument("--gtx", type=float, default=0.0)
    a.add_argument("--grx", type=float, default=0.0)
    a.add_argument("--ltx", type=float, default=0.0, help="TX feeder/connector loss dB")
    a.add_argument("--lrx", type=float, default=0.0)
    a.add_argument("--lmisc", type=float, default=0.0, help="fade/body/foliage/polarization")
    a.add_argument("--sens", type=float, help="RX sensitivity dBm")
    a.add_argument("--bw", type=freq, help="noise bandwidth")
    a.add_argument("--nf", type=float, help="RX noise figure dB")
    a.add_argument("--pl", type=float, help="override path loss (e.g. from hata)")

    a = sp.add_parser("noise", help="kTB noise floor and sensitivity")
    a.add_argument("bw", type=freq)
    a.add_argument("--nf", type=float, default=0.0)
    a.add_argument("--snr", type=float)
    a.add_argument("--temp", type=float, default=c.T0)

    a = sp.add_parser("nftemp", help="NF <-> noise temperature")
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--nf", type=float)
    g.add_argument("--te", type=float)

    a = sp.add_parser("cascade", help="Friis NF/gain/IP3 cascade; stages gain:nf[:oip3]")
    a.add_argument("stages", nargs="+")
    a.add_argument("--bw", type=freq, help="also report SFDR for this bandwidth")

    a = sp.add_parser("imd", help="two-tone IM3 level, or list mixing products")
    a.add_argument("--pin", type=float)
    a.add_argument("--iip3", type=float)
    a.add_argument("--gain", type=float, default=0.0)
    a.add_argument("--f1", type=freq)
    a.add_argument("--f2", type=freq)
    a.add_argument("--order", type=int, default=3)

    a = sp.add_parser("vswr", help="VSWR / return loss / gamma / mismatch loss")
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--vswr", type=float)
    g.add_argument("--rl", type=float)
    g.add_argument("--gamma", type=float)
    g.add_argument("--zl", type=cplx, help="load impedance, e.g. 75 or 30-20j")
    a.add_argument("--z0", type=float, default=50.0)

    a = sp.add_parser("uncertainty", help="mismatch uncertainty between two ports")
    a.add_argument("vswr1", type=float)
    a.add_argument("vswr2", type=float)

    a = sp.add_parser("cable", help="coax loss vs frequency and length")
    a.add_argument("type", help=", ".join(c.CABLES) + " or 'custom'")
    a.add_argument("f", type=freq)
    a.add_argument("length", type=dist)
    a.add_argument("--k1", type=float)
    a.add_argument("--k2", type=float)

    a = sp.add_parser("skin", help="skin depth")
    a.add_argument("f", type=freq)
    a.add_argument("--rho", type=float, default=1.68e-8, help="ohm-m (Cu 1.68e-8, Al 2.65e-8)")
    a.add_argument("--mur", type=float, default=1.0)

    a = sp.add_parser("coax", help="coax Z0 from diameters (mm)")
    a.add_argument("outer", type=float)
    a.add_argument("inner", type=float)
    a.add_argument("--er", type=float, default=1.0)

    a = sp.add_parser("microstrip", help="microstrip Z0, or width for a target Z0")
    a.add_argument("--h", type=float, required=True, help="substrate height (any unit)")
    a.add_argument("--er", type=float, required=True)
    a.add_argument("--w", type=float, help="trace width (same unit as h)")
    a.add_argument("--z0", type=float, help="solve width for this impedance")
    a.add_argument("--t", type=float, default=0.0, help="copper thickness")

    a = sp.add_parser("zin", help="input impedance of a lossless line")
    a.add_argument("--zl", type=cplx, required=True)
    a.add_argument("--z0", type=float, default=50.0)
    a.add_argument("--deg", type=float, help="electrical length in degrees")
    a.add_argument("--len", type=dist, help="physical length (needs --f)")
    a.add_argument("--f", type=freq)
    a.add_argument("--vf", type=float, default=1.0)

    a = sp.add_parser("qwt", help="quarter-wave transformer impedance")
    a.add_argument("zin", type=float)
    a.add_argument("zload", type=float)

    a = sp.add_parser("lmatch", help="L-network between two resistances")
    a.add_argument("rs", type=float)
    a.add_argument("rl", type=float)
    a.add_argument("f", type=freq)

    a = sp.add_parser("reactance", help="XL / XC / resonance")
    a.add_argument("f", type=freq, nargs="?")
    a.add_argument("--L", type=lambda t: qty(t, "H"))
    a.add_argument("--C", type=lambda t: qty(t, "F"))

    a = sp.add_parser("filter", help="LC ladder: butterworth/chebyshev lp/hp/bp")
    a.add_argument("order", type=int)
    a.add_argument("f1", type=freq, help="cutoff, or lower edge for bandpass")
    a.add_argument("--f2", type=freq, help="upper edge for bandpass")
    a.add_argument("--kind", default="butterworth", choices=["butterworth", "chebyshev"])
    a.add_argument("--resp", default="lowpass", choices=["lowpass", "highpass", "bandpass"])
    a.add_argument("--ripple", type=float, default=0.5)
    a.add_argument("--z0", type=float, default=50.0)

    a = sp.add_parser("filterorder", help="min Butterworth order for a stopband spec")
    a.add_argument("fpass", type=freq)
    a.add_argument("fstop", type=freq)
    a.add_argument("atten", type=float)

    a = sp.add_parser("fresnel", help="Fresnel zone, earth bulge, clearance at a point")
    a.add_argument("f", type=freq)
    a.add_argument("d1", type=dist)
    a.add_argument("d2", type=dist)
    a.add_argument("--zone", type=int, default=1)
    a.add_argument("--k", type=float, default=4 / 3)

    a = sp.add_parser("horizon", help="radio horizon / max line of sight")
    a.add_argument("h1", type=dist)
    a.add_argument("h2", type=dist, nargs="?", default=0.0)
    a.add_argument("--k", type=float, default=4 / 3)

    a = sp.add_parser("tworay", help="two-ray ground reflection loss")
    a.add_argument("f", type=freq)
    a.add_argument("d", type=dist)
    a.add_argument("ht", type=dist)
    a.add_argument("hr", type=dist)

    a = sp.add_parser("hata", help="Okumura-Hata / COST-231 path loss")
    a.add_argument("f", type=freq)
    a.add_argument("d", type=dist)
    a.add_argument("hb", type=dist)
    a.add_argument("hm", type=dist)
    a.add_argument("--env", default="urban", choices=["urban", "suburban", "open"])
    a.add_argument("--city", default="medium", choices=["medium", "large"])

    a = sp.add_parser("field", help="E-field from EIRP, or from received power")
    a.add_argument("--eirp", type=float, help="dBm")
    a.add_argument("--d", type=dist)
    a.add_argument("--prx", type=float, help="dBm at antenna port")
    a.add_argument("--f", type=freq)
    a.add_argument("--g", type=float, default=0.0, help="antenna gain dBi")

    a = sp.add_parser("antenna", help="dish gain/beamwidth, aperture <-> gain")
    a.add_argument("f", type=freq)
    a.add_argument("--dia", type=dist)
    a.add_argument("--gain", type=float)
    a.add_argument("--aperture", type=float, help="m^2")
    a.add_argument("--eff", type=float, default=0.55)

    a = sp.add_parser("doppler", help="Doppler shift")
    a.add_argument("f", type=freq)
    a.add_argument("v", type=float, help="m/s (knots x 0.5144)")
    a.add_argument("--angle", type=float, default=0.0)

    a = sp.add_parser("mpe", help="FCC 1.1310 RF exposure screening")
    a.add_argument("f", type=freq)
    a.add_argument("eirp_w", type=float, help="time-averaged EIRP in W")
    a.add_argument("--d", type=dist)
    a.add_argument("--occupational", action="store_true")
    a.add_argument("--no-ground", action="store_true", help="drop the 2.56 reflection factor")

    a = sp.add_parser("atc", help="aviation 8.33/25 kHz channel name <-> frequency")
    a.add_argument("value", help="channel name like 118.010, or frequency with --freq")
    a.add_argument("--freq", action="store_true", help="value is a frequency in MHz")
    a.add_argument("--spacing", type=float, default=8.33)
    return ap


def run(args):
    cmd = args.cmd
    if cmd == "convert":
        return c.convert_power(args.value, args.unit, args.z0)
    if cmd == "dbsum":
        return c.db_sum(args.levels)
    if cmd == "wavelength":
        return c.wavelength(args.f, args.vf)
    if cmd == "fspl":
        return p.fspl(args.d, args.f)
    if cmd == "link":
        return p.link_budget(args.ptx, args.gtx, args.grx, args.f, args.d, args.ltx, args.lrx,
                             args.lmisc, args.sens, args.bw, args.nf, args.pl)
    if cmd == "noise":
        return c.noise_floor(args.bw, args.nf, args.temp, args.snr)
    if cmd == "nftemp":
        return ({"Te_K": c.nf_to_temp(args.nf)} if args.nf is not None
                else {"NF_dB": c.temp_to_nf(args.te)})
    if cmd == "cascade":
        out = c.cascade(parse_stages(args.stages))
        if args.bw and "iip3_dBm" in out:
            out["sfdr"] = c.sfdr(out["iip3_dBm"], out["total_nf_db"], args.bw)
        return out
    if cmd == "imd":
        if args.f1 and args.f2:
            return c.imd_products(args.f1, args.f2, args.order)
        if args.pin is None or args.iip3 is None:
            raise ValueError("give --pin and --iip3, or --f1 and --f2")
        return c.imd3(args.pin, args.iip3, args.gain)
    if cmd == "vswr":
        return c.mismatch(args.vswr, args.rl, args.gamma, args.zl, args.z0)
    if cmd == "uncertainty":
        g1 = c.mismatch(vswr=args.vswr1)["gamma_mag"]
        g2 = c.mismatch(vswr=args.vswr2)["gamma_mag"]
        return c.mismatch_uncertainty(g1, g2)
    if cmd == "cable":
        return c.cable_loss(args.type, args.f / 1e6, args.length, args.k1, args.k2)
    if cmd == "skin":
        return c.skin_depth(args.f, args.rho, args.mur)
    if cmd == "coax":
        return c.coax_z0(args.outer, args.inner, args.er)
    if cmd == "microstrip":
        if args.z0:
            return c.microstrip_width(args.z0, args.h, args.er, args.t)
        if args.w is None:
            raise ValueError("give --w or --z0")
        return c.microstrip(args.w, args.h, args.er, args.t)
    if cmd == "zin":
        deg = args.deg
        if deg is None:
            if args.len is None or args.f is None:
                raise ValueError("give --deg, or --len with --f")
            deg = c.electrical_length(args.len, args.f, args.vf)["degrees"]
        return {"electrical_deg": deg, **c.line_input_impedance(args.zl, args.z0, deg)}
    if cmd == "qwt":
        return c.quarter_wave_transformer(args.zin, args.zload)
    if cmd == "lmatch":
        return c.l_match(args.rs, args.rl, args.f)
    if cmd == "reactance":
        if args.f is None:
            if args.L is None or args.C is None:
                raise ValueError("give f, or both --L and --C for resonance")
            return {"resonance_hz": 1 / (2 * math.pi * math.sqrt(args.L * args.C))}
        return c.reactance(args.f, args.L, args.C)
    if cmd == "filter":
        return c.lc_filter(args.order, args.f1, args.kind, args.resp, args.z0, args.ripple,
                           args.f2)
    if cmd == "filterorder":
        return c.butterworth_order(args.fpass, args.fstop, args.atten)
    if cmd == "fresnel":
        return p.fresnel(args.d1, args.d2, args.f, args.zone, args.k)
    if cmd == "horizon":
        return p.radio_horizon(args.h1, args.h2, args.k)
    if cmd == "tworay":
        return p.two_ray(args.d, args.f, args.ht, args.hr)
    if cmd == "hata":
        return p.hata(args.f / 1e6, args.d / 1e3, args.hb, args.hm, args.env, args.city)
    if cmd == "field":
        return p.field_strength(args.eirp, args.d, args.prx,
                                args.f / 1e6 if args.f else None, args.g)
    if cmd == "antenna":
        return p.antenna(args.gain, args.aperture, args.f, args.dia, args.eff)
    if cmd == "doppler":
        return p.doppler(args.v, args.f, args.angle)
    if cmd == "mpe":
        return p.mpe(args.eirp_w, args.f / 1e6, args.d, args.occupational, not args.no_ground)
    if cmd == "atc":
        if args.freq:
            return p.atc_name(float(args.value), args.spacing)
        return p.atc_channel(args.value)
    raise ValueError(f"unknown command {cmd}")


_NEG_STAGE = re.compile(r"^-[\d.]+:")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # argparse reads "-3:3" (a passive -3 dB stage) as a flag; shield it with "~"
    argv = ["~" + a[1:] if _NEG_STAGE.match(a) else a for a in argv]
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except (ValueError, ZeroDivisionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        show(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
