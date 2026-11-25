#!/usr/bin/env python3
"""Analyze Touchstone .s1p/.s2p files (VNA / sweep exports). Standard library only.

  touchstone.py ant.s1p                     summary: best match, RL/VSWR band edges
  touchstone.py ant.s1p --rl 14             bandwidth where return loss >= 14 dB
  touchstone.py filt.s2p --at 118M 137M     values at specific frequencies
  touchstone.py ant.s1p --csv out.csv       dump freq, |S|, RL, VSWR (for plotting)

If scikit-rf is installed you can go further (TDR, de-embedding, Smith plots):
  import skrf; n = skrf.Network('ant.s1p'); n.plot_s_smith()
"""
import argparse
import cmath
import csv
import math
import sys

_FREQ = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}


def parse(path):
    """Return (freqs_hz, list of matrices [n][n] complex, z0, nports)."""
    nports = int(path.lower().rsplit(".s", 1)[1].rstrip("pP"))
    unit, fmt, z0, ptype = 1e9, "ma", 50.0, "s"
    nums = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.split("!", 1)[0].strip()
            if not line:
                continue
            if line.startswith("#"):
                tok = line[1:].lower().split()
                for i, t in enumerate(tok):
                    if t in _FREQ:
                        unit = _FREQ[t]
                    elif t in ("ma", "db", "ri"):
                        fmt = t
                    elif t in ("s", "y", "z", "h", "g"):
                        ptype = t
                    elif t == "r":
                        z0 = float(tok[i + 1])
                continue
            if line.startswith("["):
                raise ValueError("Touchstone v2 keyword files are not supported; "
                                 "use scikit-rf")
            nums.extend(float(x) for x in line.split())
    if ptype != "s":
        raise ValueError(f"only S-parameters supported (file has {ptype.upper()})")
    per = 1 + 2 * nports * nports
    if len(nums) % per:
        raise ValueError("data length does not match port count")
    freqs, mats = [], []
    for k in range(0, len(nums), per):
        row = nums[k:k + per]
        freqs.append(row[0] * unit)
        vals = [_to_c(row[1 + 2 * i], row[2 + 2 * i], fmt) for i in range(nports * nports)]
        m = [[0j] * nports for _ in range(nports)]
        for idx, v in enumerate(vals):
            r, col = divmod(idx, nports)
            m[r][col] = v
        if nports == 2:  # v1 2-port order is S11 S21 S12 S22 (column-major)
            m[0][1], m[1][0] = m[1][0], m[0][1]
        mats.append(m)
    return freqs, mats, z0, nports


def _to_c(a, b, fmt):
    if fmt == "ri":
        return complex(a, b)
    mag = 10 ** (a / 20) if fmt == "db" else a
    return cmath.rect(mag, math.radians(b))


def db(x):
    return 20 * math.log10(max(abs(x), 1e-15))


def vswr(g):
    g = min(abs(g), 0.999999)
    return (1 + g) / (1 - g)


def bands_above(freqs, values, threshold):
    """Contiguous frequency ranges where value >= threshold (linear interp at edges)."""
    out, start = [], None
    for i, v in enumerate(values):
        if v >= threshold and start is None:
            start = _edge(freqs, values, i - 1, i, threshold) if i else freqs[0]
        elif v < threshold and start is not None:
            out.append((start, _edge(freqs, values, i - 1, i, threshold)))
            start = None
    if start is not None:
        out.append((start, freqs[-1]))
    return out


def _edge(f, v, i, j, t):
    if v[j] == v[i]:
        return f[j]
    return f[i] + (t - v[i]) * (f[j] - f[i]) / (v[j] - v[i])


def interp(freqs, mats, f, r, col):
    if not freqs[0] <= f <= freqs[-1]:
        raise ValueError(f"{f / 1e6:.3f} MHz outside file range")
    for i in range(1, len(freqs)):
        if freqs[i] >= f:
            t = (f - freqs[i - 1]) / (freqs[i] - freqs[i - 1])
            return mats[i - 1][r][col] * (1 - t) + mats[i][r][col] * t
    return mats[-1][r][col]


def summarize(path, rl_thresh, at, csv_path):
    freqs, mats, z0, n = parse(path)
    rl = [-db(m[0][0]) for m in mats]
    best = max(range(len(rl)), key=rl.__getitem__)
    print(f"file: {path}  ports: {n}  points: {len(freqs)}  Z0: {z0} ohm")
    print(f"span: {freqs[0] / 1e6:.4f} - {freqs[-1] / 1e6:.4f} MHz")
    g_best = mats[best][0][0]
    z_best = z0 * (1 + g_best) / (1 - g_best) if g_best != 1 else complex(math.inf)
    print(f"best match: {freqs[best] / 1e6:.4f} MHz  RL {rl[best]:.2f} dB  "
          f"VSWR {vswr(g_best):.3f}  Z {z_best.real:.1f}{z_best.imag:+.1f}j ohm")
    for lo, hi in bands_above(freqs, rl, rl_thresh):
        bw = hi - lo
        print(f"RL >= {rl_thresh} dB (VSWR <= {vswr(10 ** (-rl_thresh / 20)):.2f}): "
              f"{lo / 1e6:.4f} - {hi / 1e6:.4f} MHz  (BW {bw / 1e6:.4f} MHz, "
              f"{100 * bw / math.sqrt(lo * hi):.2f} %)")
    if n == 2:
        il = [-db(m[1][0]) for m in mats]
        b = min(range(len(il)), key=il.__getitem__)
        print(f"min insertion loss: {il[b]:.3f} dB @ {freqs[b] / 1e6:.4f} MHz")
        for lo, hi in bands_above(freqs, [-x for x in il], -il[b] - 3):
            print(f"-3 dB passband: {lo / 1e6:.4f} - {hi / 1e6:.4f} MHz")
        # group delay from S21 phase slope
        ph = [cmath.phase(m[1][0]) for m in mats]
        unwrapped = [ph[0]]
        for x in ph[1:]:
            d = x - unwrapped[-1]
            unwrapped.append(unwrapped[-1] + (d + math.pi) % (2 * math.pi) - math.pi)
        if len(freqs) > 2:
            gd = [-(unwrapped[i + 1] - unwrapped[i]) / (2 * math.pi * (freqs[i + 1] - freqs[i]))
                  for i in range(len(freqs) - 1)]
            print(f"group delay @ best IL: {gd[min(b, len(gd) - 1)] * 1e9:.3f} ns")
    for f in at or []:
        s11 = interp(freqs, mats, f, 0, 0)
        line = f"@ {f / 1e6:.4f} MHz: RL {-db(s11):.2f} dB  VSWR {vswr(s11):.3f}"
        if n == 2:
            line += f"  IL {-db(interp(freqs, mats, f, 1, 0)):.3f} dB"
        print(line)
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            head = ["freq_hz", "s11_db", "return_loss_db", "vswr"]
            w.writerow(head + (["s21_db", "s12_db", "s22_db"] if n == 2 else []))
            for f, m in zip(freqs, mats):
                row = [f, db(m[0][0]), -db(m[0][0]), vswr(m[0][0])]
                if n == 2:
                    row += [db(m[1][0]), db(m[0][1]), db(m[1][1])]
                w.writerow(row)
        print(f"wrote {csv_path}")


def _freq(t):
    from rfcalc import freq
    return freq(t)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--rl", type=float, default=10.0, help="return-loss threshold dB")
    ap.add_argument("--at", type=_freq, nargs="+")
    ap.add_argument("--csv")
    a = ap.parse_args(argv)
    try:
        summarize(a.file, a.rl, a.at, a.csv)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
