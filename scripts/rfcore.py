"""Circuit-level RF math: units, noise, linearity, mismatch, cables, lines, matching, filters.

Pure standard library. Every function returns a plain dict so the CLI can print or emit JSON.
"""
import cmath
import math

K_BOLTZMANN = 1.380649e-23  # J/K (exact, SI 2019)
T0 = 290.0  # K, IEEE reference temperature for noise figure
C0 = 299_792_458.0  # m/s
MU0 = 4e-7 * math.pi  # H/m (within 1e-9 of the CODATA value)
ETA0 = 376.730313  # ohm, free-space impedance

# Attenuation model: dB/100 ft = k1*sqrt(f_MHz) + k2*f_MHz  (conductor + dielectric loss).
# (k1, k2, velocity factor, max_MHz). CABLE_CHECKED lists cables whose fit is pinned by
# tests to published datasheet points; the rest are approximate fits to typical tables.
CABLES = {
    "lmr-195": (0.358, 0.00040, 0.80, 6000),
    "lmr-240": (0.24208, 0.00033, 0.84, 6000),
    "lmr-400": (0.12229, 0.00026, 0.85, 6000),
    "lmr-600": (0.07228, 0.00026, 0.87, 6000),
    "lmr-900": (0.04821, 0.00022, 0.87, 5000),
    "rg-58": (0.45, 0.006, 0.66, 3000),
    "rg-8x": (0.30, 0.004, 0.78, 3000),
    "rg-213": (0.20, 0.0018, 0.66, 3000),
    "ldf4-50a": (0.0660, 0.000208, 0.88, 8800),   # 1/2 in air-foam Heliax
    "ldf5-50a": (0.0358, 0.000146, 0.89, 5000),   # 7/8 in air-foam Heliax
    "ut-141": (0.4024, 0.000276, 0.70, 18000),    # 0.141 in semi-rigid, PTFE
}
CABLE_CHECKED = {
    # cable: [(MHz, dB/100ft datasheet), ...]
    "lmr-400": [(150, 1.5), (900, 3.9), (2500, 6.8), (5800, 10.8)],
    "lmr-240": [(900, 7.6), (2500, 12.9)],
}
FT_PER_M = 3.28084


# ---------- unit conversions ----------

def dbm_to_w(dbm):
    return 10 ** ((dbm - 30) / 10)


def w_to_dbm(w):
    if w <= 0:
        raise ValueError("power must be > 0 W")
    return 10 * math.log10(w) + 30


def convert_power(value, unit, z0=50.0):
    """Convert one power/voltage quantity to every common form (into z0 ohms)."""
    unit = unit.lower()
    if unit == "dbm":
        w = dbm_to_w(value)
    elif unit == "dbw":
        w = 10 ** (value / 10)
    elif unit == "w":
        w = value
    elif unit == "mw":
        w = value / 1e3
    elif unit in ("v", "vrms"):
        w = value ** 2 / z0
    elif unit == "uv":
        w = (value * 1e-6) ** 2 / z0
    elif unit in ("dbuv", "dbµv"):
        w = (10 ** (value / 20) * 1e-6) ** 2 / z0
    elif unit == "vpp":
        w = (value / (2 * math.sqrt(2))) ** 2 / z0
    else:
        raise ValueError(f"unknown unit '{unit}' (dbm, dbw, w, mw, v, vpp, uv, dbuv)")
    if w <= 0:
        raise ValueError("power must be > 0")
    vrms = math.sqrt(w * z0)
    return {
        "W": w, "mW": w * 1e3, "dBm": w_to_dbm(w), "dBW": 10 * math.log10(w),
        "Vrms": vrms, "Vpp": vrms * 2 * math.sqrt(2), "uV": vrms * 1e6,
        "dBuV": 20 * math.log10(vrms * 1e6), "z0_ohm": z0,
    }


def db_sum(levels_dbm):
    """Incoherent (power) sum of several dBm levels."""
    total = sum(dbm_to_w(x) for x in levels_dbm)
    return {"sum_dBm": w_to_dbm(total), "sum_W": total, "inputs": list(levels_dbm)}


def wavelength(f_hz, vf=1.0):
    lam = C0 * vf / f_hz
    lam0 = C0 / f_hz
    return {
        "lambda_m": lam, "half_wave_m": lam / 2, "quarter_wave_m": lam / 4,
        # Free-space dipole is cut ~2-5 % short of lambda/2 for end effect; 0.95 is the
        # classic thin-wire factor (468/f ft). Trim on the analyzer.
        "dipole_cut_m": 0.95 * lam0 / 2, "quarter_vertical_cut_m": 0.95 * lam0 / 4,
        "velocity_factor": vf,
    }


# ---------- noise and linearity ----------

def noise_floor(bw_hz, nf_db=0.0, temp_k=T0, snr_db=None):
    ktb = 10 * math.log10(K_BOLTZMANN * temp_k * bw_hz) + 30
    out = {"kTB_dBm": ktb, "kT_dBm_per_Hz": ktb - 10 * math.log10(bw_hz),
           "noise_floor_dBm": ktb + nf_db}
    if snr_db is not None:
        out["sensitivity_dBm"] = ktb + nf_db + snr_db
    return out


def nf_to_temp(nf_db):
    return T0 * (10 ** (nf_db / 10) - 1)


def temp_to_nf(te_k):
    return 10 * math.log10(1 + te_k / T0)


def cascade(stages):
    """Friis cascade. stages: list of dicts {gain_db, nf_db, oip3_dbm?}.

    Returns total gain, NF, Te, and input-referred IIP3 / output OIP3 if every stage
    gives an OIP3. A passive loss of L dB is a stage with gain -L and NF +L.
    """
    if not stages:
        raise ValueError("need at least one stage")
    f_tot, g_run = 0.0, 1.0
    inv_iip3, have_ip3 = 0.0, all(s.get("oip3_dbm") is not None for s in stages)
    rows = []
    for i, s in enumerate(stages):
        g = 10 ** (s["gain_db"] / 10)
        f = 10 ** (s["nf_db"] / 10)
        f_tot = f if i == 0 else f_tot + (f - 1) / g_run
        if have_ip3:
            iip3_stage_mw = dbm_to_w(s["oip3_dbm"] - s["gain_db"]) * 1e3
            inv_iip3 += g_run / iip3_stage_mw
        contrib = (f - 1) / g_run if i else f - 1
        rows.append({"stage": i + 1, "gain_db": s["gain_db"], "nf_db": s["nf_db"],
                     "noise_contribution_lin": contrib})
        g_run *= g
    total_nf = 10 * math.log10(f_tot)
    out = {"total_gain_db": 10 * math.log10(g_run), "total_nf_db": total_nf,
           "total_te_K": nf_to_temp(total_nf), "stages": rows}
    if have_ip3:
        iip3 = 10 * math.log10(1 / inv_iip3)
        out["iip3_dBm"] = iip3
        out["oip3_dBm"] = iip3 + out["total_gain_db"]
    return out


def sfdr(iip3_dbm, nf_db, bw_hz):
    floor = noise_floor(bw_hz, nf_db)["noise_floor_dBm"]
    return {"noise_floor_dBm": floor, "sfdr_db": 2 / 3 * (iip3_dbm - floor),
            "imd3_equals_floor_at_input_dBm": (2 * iip3_dbm + floor) / 3}


def imd3(pin_dbm, iip3_dbm, gain_db=0.0):
    """Two equal tones of pin each: third-order products at 2f1-f2, 2f2-f1."""
    out_tone = pin_dbm + gain_db
    im3_out = 3 * pin_dbm - 2 * iip3_dbm + gain_db
    return {"tone_out_dBm": out_tone, "im3_out_dBm": im3_out,
            "dBc": im3_out - out_tone}


def imd_products(f1, f2, order=3):
    """All mixing products m*f1 + n*f2 with |m|+|n| == order (positive only)."""
    prods = set()
    for m in range(-order, order + 1):
        n_abs = order - abs(m)
        for n in {n_abs, -n_abs}:
            f = m * f1 + n * f2
            if f > 0:
                prods.add((m, n, f))
    return {"order": order, "products": sorted(
        ({"m": m, "n": n, "f": f} for m, n, f in prods), key=lambda p: p["f"])}


# ---------- mismatch ----------

def mismatch(vswr=None, rl_db=None, gamma=None, zl=None, z0=50.0):
    if zl is not None:
        g = (zl - z0) / (zl + z0)
        gamma = abs(g)
        angle = math.degrees(cmath.phase(g))
    else:
        angle = None
        if vswr is not None:
            if vswr < 1:
                raise ValueError("VSWR must be >= 1")
            gamma = (vswr - 1) / (vswr + 1)
        elif rl_db is not None:
            gamma = 10 ** (-rl_db / 20)
        elif gamma is None:
            raise ValueError("give one of vswr, rl, gamma, zl")
    if not 0 <= gamma <= 1:
        raise ValueError("|gamma| must be in [0, 1]")
    out = {
        "gamma_mag": gamma,
        "vswr": math.inf if gamma == 1 else (1 + gamma) / (1 - gamma),
        "return_loss_db": math.inf if gamma == 0 else -20 * math.log10(gamma),
        "mismatch_loss_db": math.inf if gamma == 1 else -10 * math.log10(1 - gamma ** 2),
        "reflected_power_pct": 100 * gamma ** 2,
    }
    if angle is not None:
        out["gamma_angle_deg"] = angle
    return out


def mismatch_uncertainty(gamma_source, gamma_load):
    """Worst-case power-transfer uncertainty between two mismatched ports."""
    p = gamma_source * gamma_load
    return {"max_db": 20 * math.log10(1 + p), "min_db": 20 * math.log10(1 - p)}


# ---------- cables and lines ----------

def cable_loss(cable, f_mhz, length_m, k1=None, k2=None):
    key = cable.lower()
    vf = None
    if k1 is None or k2 is None:
        if key not in CABLES:
            raise ValueError(f"unknown cable '{cable}'; known: {', '.join(CABLES)} "
                             "(or pass --k1/--k2 from the datasheet)")
        k1, k2, vf, f_max = CABLES[key]
        if f_mhz > f_max:
            raise ValueError(f"{cable} is rated to {f_max} MHz")
    per100ft = k1 * math.sqrt(f_mhz) + k2 * f_mhz
    per_m = per100ft / 100 * FT_PER_M
    return {"cable": cable, "f_MHz": f_mhz, "dB_per_100ft": per100ft,
            "dB_per_100m": per_m * 100, "length_m": length_m,
            "total_loss_dB": per_m * length_m, "velocity_factor": vf,
            "checked_against_datasheet": key in CABLE_CHECKED,
            "note": "model fit; confirm against the part datasheet"}


def skin_depth(f_hz, resistivity=1.68e-8, mu_r=1.0):
    d = math.sqrt(resistivity / (math.pi * f_hz * MU0 * mu_r))
    return {"skin_depth_m": d, "skin_depth_um": d * 1e6,
            "rs_ohm_per_sq": resistivity / d}


def coax_z0(d_outer, d_inner, er=1.0):
    if d_outer <= d_inner:
        raise ValueError("outer diameter must exceed inner")
    z = ETA0 / (2 * math.pi * math.sqrt(er)) * math.log(d_outer / d_inner)
    return {"z0_ohm": z, "velocity_factor": 1 / math.sqrt(er),
            # TE11 cutoff: lambda_c ~= pi * (D + d) / 2; diameters given in mm
            "cutoff_TE11_GHz": C0 / (math.pi * (d_outer + d_inner) / 2e3 * math.sqrt(er)) / 1e9,
            "units": "diameters in mm"}


def microstrip(w, h, er, t=0.0):
    """Hammerstad-Jensen closed form (quasi-static, ~1 % for 0.1 < w/h < 10)."""
    if t > 0:  # effective width correction for strip thickness
        w = w + t / math.pi * (1 + math.log(2 * h / t))
    u = w / h
    eeff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
    if u < 1:
        eeff += (er - 1) / 2 * 0.04 * (1 - u) ** 2
        z = 60 / math.sqrt(eeff) * math.log(8 / u + u / 4)
    else:
        z = 120 * math.pi / (math.sqrt(eeff) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return {"z0_ohm": z, "eps_eff": eeff, "velocity_factor": 1 / math.sqrt(eeff),
            "w_over_h": u}


def microstrip_width(z0_target, h, er, t=0.0):
    """Bisection on width for a target impedance."""
    lo, hi = 1e-4 * h, 50 * h
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if microstrip(mid, h, er, t)["z0_ohm"] > z0_target:
            lo = mid
        else:
            hi = mid
    w = math.sqrt(lo * hi)
    return {"width": w, **microstrip(w, h, er, t)}


def line_input_impedance(zl, z0, electrical_deg):
    """Lossless line: Zin = Z0 (ZL + jZ0 tan bl) / (Z0 + jZL tan bl)."""
    t = math.tan(math.radians(electrical_deg))
    if math.isinf(t) or abs(math.cos(math.radians(electrical_deg))) < 1e-12:
        zin = z0 ** 2 / zl if zl != 0 else complex(math.inf)
    else:
        zin = z0 * (zl + 1j * z0 * t) / (z0 + 1j * zl * t)
    return {"zin_real": zin.real, "zin_imag": zin.imag, "zin_mag": abs(zin)}


def electrical_length(length_m, f_hz, vf=1.0):
    deg = 360 * length_m * f_hz / (C0 * vf)
    return {"degrees": deg, "wavelengths": deg / 360,
            "delay_ns": length_m / (C0 * vf) * 1e9}


def quarter_wave_transformer(z_in, z_load):
    return {"z_transformer_ohm": math.sqrt(z_in * z_load)}


# ---------- matching ----------

def l_match(r_source, r_load, f_hz):
    """Both L-network solutions between two real resistances."""
    if r_source == r_load:
        return {"note": "already matched"}
    r_hi, r_lo = max(r_source, r_load), min(r_source, r_load)
    q = math.sqrt(r_hi / r_lo - 1)
    xs, xp = q * r_lo, r_hi / q
    w = 2 * math.pi * f_hz
    shunt_side = "source" if r_source > r_load else "load"
    return {
        "Q": q, "bandwidth_hz_approx": f_hz / q, "shunt_element_on": shunt_side + " side (higher R)",
        "lowpass": {"series_L_H": xs / w, "shunt_C_F": 1 / (w * xp)},
        "highpass": {"series_C_F": 1 / (w * xs), "shunt_L_H": xp / w},
    }


def reactance(f_hz, l_h=None, c_f=None):
    w = 2 * math.pi * f_hz
    out = {}
    if l_h is not None:
        out["XL_ohm"] = w * l_h
    if c_f is not None:
        out["XC_ohm"] = 1 / (w * c_f)
    if l_h is not None and c_f is not None:
        out["resonance_hz"] = 1 / (2 * math.pi * math.sqrt(l_h * c_f))
    return out


# ---------- filters ----------

def prototype(n, kind="butterworth", ripple_db=0.5):
    if n < 1 or n > 15:
        raise ValueError("order must be 1..15")
    if kind == "bessel":
        from rfdesign import bessel_g  # lazy: rfdesign imports rfcore
        return bessel_g(n), 1.0
    if kind == "butterworth":
        g = [2 * math.sin((2 * k - 1) * math.pi / (2 * n)) for k in range(1, n + 1)]
        return g, 1.0
    if kind != "chebyshev":
        raise ValueError("kind is butterworth, chebyshev or bessel")
    beta = math.log(1 / math.tanh(ripple_db / 17.37))
    gam = math.sinh(beta / (2 * n))
    a = [math.sin((2 * k - 1) * math.pi / (2 * n)) for k in range(1, n + 1)]
    b = [gam ** 2 + math.sin(k * math.pi / n) ** 2 for k in range(1, n + 1)]
    g = [2 * a[0] / gam]
    for k in range(1, n):
        g.append(4 * a[k - 1] * a[k] / (b[k - 1] * g[k - 1]))
    g_load = 1.0 if n % 2 else 1 / math.tanh(beta / 4) ** 2
    return g, g_load


def lc_filter(n, f1_hz, kind="butterworth", response="lowpass", z0=50.0,
              ripple_db=0.5, f2_hz=None):
    """Shunt-first ladder. Element 1 is shunt, 2 series, alternating."""
    g, g_load = prototype(n, kind, ripple_db)
    elems = []
    if response in ("lowpass", "highpass"):
        w = 2 * math.pi * f1_hz
        for i, gk in enumerate(g):
            shunt = i % 2 == 0
            if response == "lowpass":
                e = {"C_F": gk / (z0 * w)} if shunt else {"L_H": gk * z0 / w}
            else:
                e = {"L_H": z0 / (gk * w)} if shunt else {"C_F": 1 / (gk * z0 * w)}
            elems.append({"pos": i + 1, "topology": "shunt" if shunt else "series", **e})
    elif response == "bandpass":
        if not f2_hz or f2_hz <= f1_hz:
            raise ValueError("bandpass needs f2 > f1")
        w0 = 2 * math.pi * math.sqrt(f1_hz * f2_hz)
        fbw = (f2_hz - f1_hz) / math.sqrt(f1_hz * f2_hz)
        for i, gk in enumerate(g):
            if i % 2 == 0:  # shunt parallel LC
                e = {"topology": "shunt parallel LC", "C_F": gk / (w0 * fbw * z0),
                     "L_H": fbw * z0 / (w0 * gk)}
            else:  # series LC
                e = {"topology": "series LC", "L_H": gk * z0 / (w0 * fbw),
                     "C_F": fbw / (w0 * gk * z0)}
            elems.append({"pos": i + 1, **e})
    else:
        raise ValueError("response: lowpass, highpass, bandpass")
    out = {"g": g, "g_load": g_load, "elements": elems, "z0": z0}
    if g_load != 1.0:
        out["warning"] = (f"even-order Chebyshev: load must be {g_load * z0:.2f} ohm "
                          "(or use an odd order for equal terminations)")
    return out


def butterworth_order(f_pass, f_stop, atten_db, pass_ripple_db=3.0):
    """Minimum order for lowpass (frequencies as ratio) to hit atten at f_stop."""
    ratio = f_stop / f_pass
    if ratio <= 1:
        raise ValueError("f_stop must exceed f_pass")
    eps2 = 10 ** (pass_ripple_db / 10) - 1
    n = math.log10((10 ** (atten_db / 10) - 1) / eps2) / (2 * math.log10(ratio))
    return {"min_order": math.ceil(n), "exact": n}
