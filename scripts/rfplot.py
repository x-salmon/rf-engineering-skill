#!/usr/bin/env python3
"""Optional plots (needs matplotlib). Each command writes a PNG.

  rfplot.py smith ant.s1p --out smith.png
  rfplot.py sweep filt.s2p --out sweep.png
  rfplot.py filter 5 --kind chebyshev --ripple 0.5 --out resp.png
  rfplot.py profile path.csv --f 6GHz --htx 30 --hrx 20 --out path.png
  rfplot.py array 8 0.5 --steer 20 --out af.png
"""
import argparse
import math
import sys

import rfcore
import rfdesign
import rfpath
import touchstone
from rfargs import dist, freq


def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        sys.exit("plots need matplotlib: pip install matplotlib")
    return plt


def smith(path, out):
    plt = _plt()
    f, mats, _, _ = touchstone.parse(path)
    fig, ax = plt.subplots(figsize=(6, 6))
    t = [i * 2 * math.pi / 360 for i in range(361)]
    for r in (0, 0.2, 0.5, 1, 2, 5):  # constant-resistance circles
        c, rad = r / (1 + r), 1 / (1 + r)
        ax.plot([c + rad * math.cos(a) for a in t], [rad * math.sin(a) for a in t],
                color="0.85", lw=0.7)
    for x in (0.2, 0.5, 1, 2, 5):  # constant-reactance arcs, clipped to the unit circle
        for sx in (x, -x):
            pts = []
            for a in t:
                gx, gy = 1 + math.cos(a) / sx, 1 / sx + math.sin(a) / sx
                if gx * gx + gy * gy <= 1.0001:
                    pts.append((gx, gy))
            if pts:
                ax.plot(*zip(*pts), color="0.85", lw=0.7, ls="none", marker=".", ms=0.6)
    ax.plot([m[0][0].real for m in mats], [m[0][0].imag for m in mats], lw=1.6)
    ax.plot(mats[0][0][0].real, mats[0][0][0].imag, "o", label=f"{f[0] / 1e6:.2f} MHz")
    ax.plot(mats[-1][0][0].real, mats[-1][0][0].imag, "s", label=f"{f[-1] / 1e6:.2f} MHz")
    ax.set_aspect("equal")
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.axis("off")
    ax.legend(loc="lower right")
    ax.set_title(f"S11 {path}")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    return out


def sweep(path, out):
    plt = _plt()
    f, mats, _, n = touchstone.parse(path)
    mhz = [x / 1e6 for x in f]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(mhz, [touchstone.db(m[0][0]) for m in mats], label="S11")
    if n == 2:
        ax.plot(mhz, [touchstone.db(m[1][0]) for m in mats], label="S21")
    ax.set_xlabel("MHz")
    ax.set_ylabel("dB")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    return out


def filter_resp(order, kind, ripple, out):
    plt = _plt()
    g, _ = rfcore.prototype(order, kind, ripple)
    w = [10 ** (-2 + 3 * i / 600) for i in range(601)]
    resp = rfdesign.response(g, w)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    a1.semilogx(w, [r["S21_dB"] for r in resp])
    a1.set_ylabel("|S21| dB")
    a1.set_ylim(-80, 3)
    a2.semilogx(w, [r["group_delay_norm"] for r in resp])
    a2.set_ylabel("group delay (norm s)")
    a2.set_xlabel("normalized frequency (rad/s)")
    for a in (a1, a2):
        a.grid(alpha=0.3, which="both")
    a1.set_title(f"{kind} n={order}")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    return out


def profile_plot(csv_path, f_hz, htx, hrx, k, out):
    plt = _plt()
    prof = rfpath.load_profile_csv(csv_path)
    res = rfpath.analyze_profile(prof, f_hz, htx, hrx, k)
    pts = res["points"]
    x = [p["d_m"] / 1e3 for p in pts]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.fill_between(x, [p["effective_m"] for p in pts], min(p["terrain_m"] for p in pts) - 10,
                    color="tan", label=f"terrain + earth bulge (k={k:.3g})")
    ax.plot(x, [p["los_m"] for p in pts], "k-", lw=1, label="line of sight")
    ax.plot(x, [p["los_m"] - p["f1_m"] for p in pts], "b--", lw=0.8, label="F1 lower edge")
    ax.plot(x, [p["los_m"] - 0.6 * p["f1_m"] for p in pts], "g:", lw=0.8, label="60 % F1")
    ax.set_xlabel("km")
    ax.set_ylabel("m")
    ax.legend()
    ax.set_title(f"clearance {res['worst_clearance_pct_F1']:.0f} % F1, "
                 f"diffraction {res['diffraction_loss_db']:.1f} dB")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    return out


def array_plot(n, d_wl, steer, out):
    plt = _plt()
    kd = 2 * math.pi * d_wl
    beta = -kd * math.sin(math.radians(steer))
    th = [math.radians(-90 + i * 0.25) for i in range(721)]
    vals = []
    for t in th:
        psi = kd * math.sin(t) + beta
        s = math.sin(psi / 2)
        af = 1.0 if abs(s) < 1e-12 else abs(math.sin(n * psi / 2) / (n * s))
        vals.append(max(20 * math.log10(max(af, 1e-6)), -40))
    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(projection="polar")
    ax.plot(th, vals)
    ax.set_thetamin(-90)
    ax.set_thetamax(90)
    ax.set_theta_zero_location("N")
    ax.set_rlim(-40, 0)
    ax.set_title(f"N={n}, d={d_wl} wl, steer {steer} deg")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("smith")
    a.add_argument("file")
    a = sp.add_parser("sweep")
    a.add_argument("file")
    a = sp.add_parser("filter")
    a.add_argument("order", type=int)
    a.add_argument("--kind", default="butterworth", choices=["butterworth", "chebyshev", "bessel"])
    a.add_argument("--ripple", type=float, default=0.5)
    a = sp.add_parser("profile")
    a.add_argument("csv")
    a.add_argument("--f", type=freq, required=True)
    a.add_argument("--htx", type=dist, required=True)
    a.add_argument("--hrx", type=dist, required=True)
    a.add_argument("--k", type=float, default=4 / 3)
    a = sp.add_parser("array")
    a.add_argument("n", type=int)
    a.add_argument("spacing_wl", type=float)
    a.add_argument("--steer", type=float, default=0.0)
    for p in sp.choices.values():
        p.add_argument("--out", default="plot.png")
    x = ap.parse_args(argv)
    try:
        if x.cmd == "smith":
            path = smith(x.file, x.out)
        elif x.cmd == "sweep":
            path = sweep(x.file, x.out)
        elif x.cmd == "filter":
            path = filter_resp(x.order, x.kind, x.ripple, x.out)
        elif x.cmd == "profile":
            path = profile_plot(x.csv, x.f, x.htx, x.hrx, x.k, x.out)
        else:
            path = array_plot(x.n, x.spacing_wl, x.steer, x.out)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
