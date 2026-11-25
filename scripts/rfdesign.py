"""Filter synthesis (Bessel ladder, elliptic via scipy), Pi/T/stub matching, E-series values,
antenna arrays, antenna isolation, helix and patch starting dimensions."""
import bisect
import cmath
import math

from rfargs import cplx, dist, freq, qty
from rfcore import C0

# ---------- polynomials (ascending coefficients) ----------


def _pmul(a, b):
    out = [0j] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def _peval(p, s):
    acc = 0j
    for c in reversed(p):
        acc = acc * s + c
    return acc


def _roots(p):
    """Durand-Kerner with Newton polish. p ascending, leading coefficient non-zero."""
    p = [complex(c) for c in p]
    while abs(p[-1]) == 0:
        p.pop()
    n = len(p) - 1
    monic = [c / p[-1] for c in p]
    rad = 1 + max(abs(c) for c in monic[:-1])
    z = [rad * cmath.exp(2j * math.pi * (k + 0.25) / n) for k in range(n)]
    for _ in range(2000):
        delta = 0.0
        for i in range(n):
            den = 1
            for j in range(n):
                if i != j:
                    den *= z[i] - z[j]
            step = _peval(monic, z[i]) / den
            z[i] -= step
            delta = max(delta, abs(step))
        if delta < 1e-14:
            break
    dp = [k * monic[k] for k in range(1, n + 1)]
    for i in range(n):
        for _ in range(5):
            d = _peval(dp, z[i])
            if d == 0:
                break
            z[i] -= _peval(monic, z[i]) / d
    return z


def bessel_poly(n):
    """Reverse Bessel polynomial theta_n(s), ascending; delay = 1 s at DC."""
    return [math.factorial(2 * n - k) / (2 ** (n - k) * math.factorial(k)
                                         * math.factorial(n - k)) for k in range(n + 1)]


def allpole_ladder(d):
    """Equal-termination LC ladder g-values for S21 = D(0)/D(s) (Darlington synthesis)."""
    n = len(d) - 1
    k = d[0]
    d_neg = [c * (-1) ** i for i, c in enumerate(d)]
    p = [complex(c) for c in _pmul(d, d_neg)]
    p[0] -= k * k  # N(s)N(-s) = D(s)D(-s) - K^2
    zeros_at_origin = 0
    while abs(p[0]) < 1e-9 * max(abs(c) for c in p):
        p.pop(0)
        zeros_at_origin += 1
    r = _roots(p) if len(p) > 1 else []
    lhp = sorted(r, key=lambda z: z.real)[: n - zeros_at_origin // 2]
    nr = [complex(d[-1])]
    for z in lhp:
        nr = _pmul(nr, [-z, 1])
    nr = [0j] * (zeros_at_origin // 2) + nr
    nr = [c.real for c in nr]
    a = [x + y for x, y in zip(d, nr)]
    b = [x - y for x, y in zip(d, nr)]
    return _cauer(a, b, n)


def _cauer(a, b, n):
    """Continued fraction at infinity of A/B -> g-values."""
    g = []
    a, b = a[:], b[:]
    for _ in range(n):
        while len(b) > 1 and abs(b[-1]) < 1e-12 * max(abs(x) for x in b):
            b.pop()
        while len(a) > 1 and abs(a[-1]) < 1e-12 * max(abs(x) for x in a):
            a.pop()
        if len(a) != len(b) + 1:
            raise ValueError("synthesis failed: degree mismatch")
        q = a[-1] / b[-1]
        g.append(q)
        rem = a[:]
        for i, c in enumerate(b):
            rem[i + 1] -= q * c
        rem.pop()
        a, b = b, rem
    return g


def ladder_s21(g, w):
    """S21 of a shunt-first normalized ladder (1 ohm both ends) at w rad/s."""
    a, b, c, d = 1, 0, 0, 1
    for i, gk in enumerate(g):
        if i % 2 == 0:
            m = (1, 0, 1j * w * gk, 1)
        else:
            m = (1, 1j * w * gk, 0, 1)
        a, b, c, d = (a * m[0] + b * m[2], a * m[1] + b * m[3],
                      c * m[0] + d * m[2], c * m[1] + d * m[3])
    return 2 / (a + b + c + d)


def bessel_g(n, normalize="3db"):
    d = bessel_poly(n)
    g = allpole_ladder(d)
    if normalize == "delay":
        return g
    lo, hi = 0.01, 10.0 * n
    for _ in range(200):
        mid = (lo + hi) / 2
        if abs(d[0] / _peval(d, 1j * mid)) ** 2 > 0.5:
            lo = mid
        else:
            hi = mid
    return [x * lo for x in g]


def response(g, w_list):
    """|S21| dB and group delay (normalized seconds) of a ladder."""
    out = []
    for w in w_list:
        h = 1e-6 * max(w, 1e-3)
        ph1 = cmath.phase(ladder_s21(g, w - h))
        ph2 = cmath.phase(ladder_s21(g, w + h))
        dph = (ph2 - ph1 + math.pi) % (2 * math.pi) - math.pi
        out.append({"w_norm": w, "S21_dB": 20 * math.log10(abs(ladder_s21(g, w))),
                    "group_delay_norm": -dph / (2 * h)})
    return out


def elliptic(f_pass, f_stop, ripple_db, atten_db):
    try:
        from scipy import signal
    except ImportError as exc:
        raise ValueError("elliptic design needs scipy: pip install scipy") from exc
    wp, ws = 2 * math.pi * f_pass, 2 * math.pi * f_stop
    n, wn = signal.ellipord(wp, ws, ripple_db, atten_db, analog=True)
    z, p, _ = signal.ellip(n, ripple_db, atten_db, wn, analog=True, output="zpk")
    notches = sorted({round(abs(x.imag) / (2 * math.pi), 3) for x in z})
    return {"order": int(n), "notch_frequencies_hz": notches,
            "poles": [f"{x.real:.4g}{x.imag:+.4g}j" for x in p],
            "note": "LC element synthesis for elliptic (zero-shifting) is not automated; "
                    "use the order and notches with a filter tool, or use chebyshev"}


# ---------- matching ----------

def pi_match(rs, rl, f_hz, q):
    r_hi = max(rs, rl)
    q_min = math.sqrt(r_hi / min(rs, rl) - 1)
    if q <= q_min:
        raise ValueError(f"Q must exceed {q_min:.3f} for these resistances")
    rv = r_hi / (q * q + 1)
    q1, q2 = math.sqrt(rs / rv - 1), math.sqrt(rl / rv - 1)
    w = 2 * math.pi * f_hz
    xc1, xc2, xl = rs / q1, rl / q2, rv * (q1 + q2)
    return {"topology": "lowpass Pi: shunt C1 (source) - series L - shunt C2 (load)",
            "virtual_R_ohm": rv, "C1_F": 1 / (w * xc1), "L_H": xl / w, "C2_F": 1 / (w * xc2),
            "loaded_Q": q, "bandwidth_hz_approx": f_hz / q}


def t_match(rs, rl, f_hz, q):
    r_lo = min(rs, rl)
    q_min = math.sqrt(max(rs, rl) / r_lo - 1)
    if q <= q_min:
        raise ValueError(f"Q must exceed {q_min:.3f} for these resistances")
    rv = r_lo * (q * q + 1)
    q1, q2 = math.sqrt(rv / rs - 1), math.sqrt(rv / rl - 1)
    w = 2 * math.pi * f_hz
    return {"topology": "lowpass T: series L1 (source) - shunt C - series L2 (load)",
            "virtual_R_ohm": rv, "L1_H": q1 * rs / w, "C_F": (q1 + q2) / (w * rv),
            "L2_H": q2 * rl / w, "loaded_Q": q, "bandwidth_hz_approx": f_hz / q}


def _line_y(zl, z0, beta_l):
    t = math.tan(beta_l)
    return 1 / (z0 * (zl + 1j * z0 * t) / (z0 + 1j * zl * t))


def _stub_len(b_needed, y0, short):
    """Electrical length (wavelengths) of a stub with input susceptance b_needed."""
    if short:  # Y = -j Y0 cot(bl)
        bl = math.atan2(-y0, b_needed) if b_needed else math.pi / 2
    else:  # Y = j Y0 tan(bl)
        bl = math.atan(b_needed / y0)
    return (bl / (2 * math.pi)) % 0.5


def single_stub(zl, z0=50.0, short=True):
    """Shunt single-stub: solve d by sweeping, then verify the match numerically."""
    y0 = 1 / z0
    sols = []
    steps = 20000
    prev = None
    for i in range(steps + 1):
        d = 0.5 * i / steps
        g = _line_y(zl, z0, 2 * math.pi * d).real - y0
        if prev is not None and prev[1] * g < 0:
            lo, hi = prev[0], d
            for _ in range(80):
                mid = (lo + hi) / 2
                gm = _line_y(zl, z0, 2 * math.pi * mid).real - y0
                if (gm < 0) == (_line_y(zl, z0, 2 * math.pi * lo).real - y0 < 0):
                    lo = mid
                else:
                    hi = mid
            sols.append((lo + hi) / 2)
        prev = (d, g)
    out = []
    for d in sols:
        y = _line_y(zl, z0, 2 * math.pi * d)
        length = _stub_len(-y.imag, y0, short)
        stub_y = (-1j * y0 / math.tan(2 * math.pi * length) if short
                  else 1j * y0 * math.tan(2 * math.pi * length))
        resid = abs((y + stub_y) / y0 - 1)
        out.append({"d_wavelengths": d, "stub_wavelengths": length,
                    "stub": "short" if short else "open", "verify_residual": resid})
    if not out:
        raise ValueError("no solution (is the load already matched or purely reactive?)")
    return {"solutions": out}


def double_stub(zl, z0=50.0, spacing_wl=0.125, short=True):
    """Two shunt stubs, the first at the load, spaced spacing_wl. Numeric solve + verify."""
    y0 = 1 / z0
    yl = 1 / zl
    t = math.tan(2 * math.pi * spacing_wl)
    gl, bl = yl.real, yl.imag
    if gl > y0 * (1 + t * t) / (t * t):
        raise ValueError("load in the forbidden region; add a line section or change spacing")
    out = []
    root = math.sqrt((1 + t * t) * gl * y0 - gl * gl * t * t)
    for sgn in (1, -1):
        b1 = -bl + (y0 + sgn * root) / t
        y_after1 = gl + 1j * (bl + b1)
        y_at2 = _line_y(1 / y_after1, z0, 2 * math.pi * spacing_wl)
        b2 = -y_at2.imag
        l1, l2 = _stub_len(b1, y0, short), _stub_len(b2, y0, short)
        resid = abs((y_at2 + 1j * b2) / y0 - 1)
        out.append({"stub1_wavelengths": l1, "stub2_wavelengths": l2,
                    "verify_residual": resid})
    return {"spacing_wavelengths": spacing_wl, "stub": "short" if short else "open",
            "solutions": out}


# ---------- E-series ----------

E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.3, 4.7,
       5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]
SERIES = {"E6": E24[::4], "E12": E24[::2], "E24": E24,
          "E96": [round(10 ** (i / 96), 2) for i in range(96)]}


def nearest(value, series="E24"):
    vals = SERIES[series.upper()]
    if value <= 0:
        raise ValueError("value must be > 0")
    exp = math.floor(math.log10(value))
    mant = value / 10 ** exp
    cands = vals + [10.0]
    i = bisect.bisect_left(cands, mant)
    best = min(cands[max(i - 1, 0): i + 1], key=lambda c: abs(math.log(c / mant)))
    snapped = best * 10 ** exp
    return {"value": value, "nearest": snapped, "error_pct": 100 * (snapped / value - 1),
            "series": series.upper()}


# ---------- antennas ----------

def array_factor(n, d_wl, steer_deg=0.0, theta_deg=None):
    """Uniform linear array; angles from broadside."""
    kd = 2 * math.pi * d_wl
    beta = -kd * math.sin(math.radians(steer_deg))

    def af(th):
        psi = kd * math.sin(math.radians(th)) + beta
        if abs(math.sin(psi / 2)) < 1e-12:
            return 1.0
        return abs(math.sin(n * psi / 2) / (n * math.sin(psi / 2)))

    lo = hi = steer_deg
    while lo > -90 and af(lo) ** 2 > 0.5:
        lo -= 0.01
    while hi < 90 and af(hi) ** 2 > 0.5:
        hi += 0.01
    out = {"elements": n, "spacing_wl": d_wl, "steer_deg": steer_deg,
           "hpbw_deg": hi - lo, "array_gain_db_approx": 10 * math.log10(n),
           "max_grating_free_steer_deg": (math.degrees(math.asin(min(1 / d_wl - 1, 1)))
                                          if d_wl < 1 else 0.0),
           "progressive_phase_deg": math.degrees(beta)}
    if d_wl * (1 + abs(math.sin(math.radians(steer_deg)))) >= 1:
        out["warning"] = "grating lobe present at this spacing/steer"
    if theta_deg is not None:
        out["AF_dB_at_theta"] = 20 * math.log10(max(af(theta_deg), 1e-12))
    return out


def isolation(f_hz, sep_m, mode="horizontal", g1_dbi=2.15, g2_dbi=2.15):
    lam = C0 / f_hz
    if mode == "horizontal":
        iso = 22 + 20 * math.log10(sep_m / lam) - (g1_dbi + g2_dbi)
        note = "free-space Friis between main lobes; valid for separation >> lambda"
    else:
        iso = 28 + 40 * math.log10(sep_m / lam)
        note = "empirical vertical-stack rule for collinear dipoles, separation > lambda"
    return {"isolation_db": iso, "separation_wl": sep_m / lam, "note": note}


def helix(f_hz, turns, spacing_wl=0.25):
    lam = C0 / f_hz
    c = lam
    s = spacing_wl * lam
    g = 10 * math.log10(15 * c * c * turns * s / lam ** 3)
    return {"diameter_m": c / math.pi, "turn_spacing_m": s,
            "pitch_deg": math.degrees(math.atan(s / c)), "axial_length_m": turns * s,
            "gain_dBi_kraus": g, "gain_note": "Kraus formula is optimistic by ~2-3 dB",
            "hpbw_deg": 52 / (c / lam * math.sqrt(turns * s / lam)),
            "input_R_ohm": 140 * c / lam, "ground_plane_min_m": 0.75 * lam}


def patch(f_hz, er, h_m):
    """Rectangular microstrip patch, transmission-line model (Balanis)."""
    w = C0 / (2 * f_hz) * math.sqrt(2 / (er + 1))
    eeff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 * h_m / w) ** -0.5
    dl = 0.412 * h_m * (eeff + 0.3) * (w / h_m + 0.264) / ((eeff - 0.258) * (w / h_m + 0.8))
    length = C0 / (2 * f_hz * math.sqrt(eeff)) - 2 * dl
    lam = C0 / f_hz
    g1 = w / (120 * lam) * (1 - (2 * math.pi * h_m / lam) ** 2 / 24)
    r_edge = 1 / (2 * g1)
    inset = None
    if r_edge > 50:
        inset = length / math.pi * math.acos(math.sqrt(50 / r_edge))
    return {"width_m": w, "length_m": length, "eps_eff": eeff, "delta_L_m": dl,
            "edge_R_ohm_approx": r_edge, "inset_feed_for_50_ohm_m": inset,
            "note": "starting point; tune in an EM solver (mutual G12 ignored)"}


# ---------- CLI ----------

def register(sp):
    a = sp.add_parser("bessel", help="Bessel (max-flat delay) ladder + response check")
    a.add_argument("order", type=int)
    a.add_argument("--norm", choices=["3db", "delay"], default="3db")
    a.set_defaults(func=lambda x: _bessel_cmd(x.order, x.norm))

    a = sp.add_parser("elliptic", help="elliptic (Cauer) order and notch frequencies (scipy)")
    a.add_argument("fpass", type=freq)
    a.add_argument("fstop", type=freq)
    a.add_argument("--ripple", type=float, default=0.5)
    a.add_argument("--atten", type=float, default=50.0)
    a.set_defaults(func=lambda x: elliptic(x.fpass, x.fstop, x.ripple, x.atten))

    for name, fn in (("pimatch", pi_match), ("tmatch", t_match)):
        a = sp.add_parser(name, help=f"{name[:1].upper()}-network match with chosen Q")
        a.add_argument("rs", type=float)
        a.add_argument("rl", type=float)
        a.add_argument("f", type=freq)
        a.add_argument("--q", type=float, required=True)
        a.set_defaults(func=lambda x, fn=fn: fn(x.rs, x.rl, x.f, x.q))

    a = sp.add_parser("stub", help="single or double shunt-stub match")
    a.add_argument("zl", type=cplx)
    a.add_argument("--z0", type=float, default=50.0)
    a.add_argument("--open", action="store_true", help="open stubs instead of shorted")
    a.add_argument("--double", type=float, metavar="SPACING_WL",
                   help="double stub with this spacing in wavelengths (e.g. 0.125)")
    a.set_defaults(func=lambda x: (double_stub(x.zl, x.z0, x.double, not x.open) if x.double
                                   else single_stub(x.zl, x.z0, not x.open)))

    a = sp.add_parser("eseries", help="nearest standard E6/E12/E24/E96 value")
    a.add_argument("value", type=qty)
    a.add_argument("--series", default="E24", choices=list(SERIES))
    a.set_defaults(func=lambda x: nearest(x.value, x.series))

    a = sp.add_parser("array", help="uniform linear array beamwidth, steering, grating lobes")
    a.add_argument("n", type=int)
    a.add_argument("spacing_wl", type=float)
    a.add_argument("--steer", type=float, default=0.0)
    a.add_argument("--theta", type=float)
    a.set_defaults(func=lambda x: array_factor(x.n, x.spacing_wl, x.steer, x.theta))

    a = sp.add_parser("isolation", help="antenna-to-antenna isolation (horizontal/vertical)")
    a.add_argument("f", type=freq)
    a.add_argument("sep", type=dist)
    a.add_argument("--mode", choices=["horizontal", "vertical"], default="horizontal")
    a.add_argument("--g1", type=float, default=2.15)
    a.add_argument("--g2", type=float, default=2.15)
    a.set_defaults(func=lambda x: isolation(x.f, x.sep, x.mode, x.g1, x.g2))

    a = sp.add_parser("helix", help="axial-mode helix dimensions (Kraus)")
    a.add_argument("f", type=freq)
    a.add_argument("turns", type=int)
    a.add_argument("--spacing", type=float, default=0.25)
    a.set_defaults(func=lambda x: helix(x.f, x.turns, x.spacing))

    a = sp.add_parser("patch", help="rectangular microstrip patch dimensions")
    a.add_argument("f", type=freq)
    a.add_argument("--er", type=float, required=True)
    a.add_argument("--h", type=dist, required=True)
    a.set_defaults(func=lambda x: patch(x.f, x.er, x.h))


def _bessel_cmd(n, norm):
    g = bessel_g(n, norm)
    pts = response(g, [0.01, 0.5, 1.0, 2.0])
    return {"g": g, "normalization": "-3 dB at 1 rad/s" if norm == "3db"
            else "1 s group delay at DC", "response_check": pts,
            "use": f"rfcalc filter {n} <fc> --kind bessel scales these to real parts"}

