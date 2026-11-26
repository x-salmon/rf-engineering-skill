"""Link budgets: EIRP, sensitivity, fade margin, ground-reflection path loss, Fresnel clearance at
an obstacle, max-range solving, and radar / passive-RF detection range for small aircraft.

Formulas and sources: references/link-budget.md. Everything here is generic textbook engineering.
"""
import cmath
import math

from rfargs import dist, freq, qty
from rfcomms import radar
from rfcore import C0, T0, dbm_to_w, noise_floor
from rfpath import knife_edge_loss
from rfprop import EARTH_R_KM, fspl, radio_horizon

# Typical ground constants (relative permittivity, conductivity S/m) after ITU-R P.527 curves
# at VHF/UHF. They vary with frequency and moisture; "pec" is the ideal reflector (gamma = -1).
GROUNDS = {"pec": None, "sea": (70.0, 5.0), "fresh-water": (80.0, 3e-3),
           "wet": (30.0, 1e-2), "average": (15.0, 1e-3), "dry": (3.0, 1e-4)}
SCAN_POINTS = 4000
SCAN_MIN_M = 1.0
SCAN_MAX_M = 2e6


# ---------- powers ----------

def eirp(p_tx_dbm, g_tx_dbi=0.0, l_tx_db=0.0):
    e = p_tx_dbm - l_tx_db + g_tx_dbi
    return {"eirp_dBm": e, "eirp_dBW": e - 30, "eirp_W": dbm_to_w(e), "erp_dBm": e - 2.15,
            "erp_W": dbm_to_w(e - 2.15)}


def sensitivity(bw_hz, nf_db, snr_db, temp_k=T0):
    """Sensitivity = kTB + NF + required SNR (all in dB)."""
    n = noise_floor(bw_hz, nf_db, temp_k, snr_db)
    return {"noise_floor_dBm": n["noise_floor_dBm"], "sensitivity_dBm": n["sensitivity_dBm"],
            "kTB_dBm": n["kTB_dBm"]}


def rayleigh_fade_margin(reliability):
    """Margin so a Rayleigh-faded signal stays above threshold `reliability` of the time.

    P(r^2 < F * mean) = 1 - exp(-1/F)  ->  F = -1 / ln(reliability).
    """
    if not 0 < reliability < 1:
        raise ValueError("reliability must be between 0 and 1 (e.g. 0.99)")
    return -10 * math.log10(-math.log(reliability))


def rayleigh_reliability(margin_db):
    return math.exp(-10 ** (-margin_db / 10))


def fade_margin(reliability=None, margin_db=None):
    """reliability is a fraction (0.999); the CLI converts its percent argument."""
    if margin_db is not None and reliability is not None:
        raise ValueError("give a reliability or a fade margin, not both")
    if margin_db is not None:
        return {"fade_margin_db": margin_db,
                "rayleigh_reliability_pct": 100 * rayleigh_reliability(margin_db)}
    if reliability is None:
        raise ValueError("give a reliability (e.g. 99.9 %) or a fade margin")
    r = reliability
    return {"reliability_pct": 100 * r, "fade_margin_db": rayleigh_fade_margin(r),
            "outage_pct": 100 * (1 - r), "model": "Rayleigh (no line-of-sight component)"}


# ---------- path loss ----------

def ground_gamma(psi_rad, f_hz, ground="average", pol="v"):
    """Fresnel reflection coefficient at grazing angle psi for a lossy flat ground."""
    if GROUNDS.get(ground, "missing") == "missing":
        raise ValueError(f"ground must be one of {', '.join(GROUNDS)}")
    if GROUNDS[ground] is None:
        return complex(-1, 0)
    er, sigma = GROUNDS[ground]
    ec = complex(er, -60 * sigma * C0 / f_hz)
    s, root = math.sin(psi_rad), cmath.sqrt(ec - math.cos(psi_rad) ** 2)
    if pol == "h":
        return (s - root) / (s + root)
    if pol == "v":
        return (ec * s - root) / (ec * s + root)
    raise ValueError("pol must be h or v")


def two_ray_ground(d_m, f_hz, ht_m, hr_m, ground="average", pol="v"):
    """Flat-earth two-ray loss with a direct ray and one ground-reflected ray."""
    if min(d_m, ht_m, hr_m) <= 0:
        raise ValueError("distance and both heights must be > 0")
    lam = C0 / f_hz
    d_dir = math.hypot(d_m, ht_m - hr_m)
    d_ref = math.hypot(d_m, ht_m + hr_m)
    psi = math.atan2(ht_m + hr_m, d_m)
    g = ground_gamma(psi, f_hz, ground, pol)
    phase = 2 * math.pi * (d_ref - d_dir) / lam
    factor = abs(1 + g * (d_dir / d_ref) * cmath.exp(-1j * phase))
    loss = fspl(d_dir, f_hz)["fspl_db"] - 20 * math.log10(max(factor, 1e-12))
    return {"path_loss_db": loss, "fspl_db": fspl(d_m, f_hz)["fspl_db"],
            "two_ray_far_db": 40 * math.log10(d_m) - 20 * math.log10(ht_m * hr_m),
            "crossover_m": 4 * math.pi * ht_m * hr_m / lam,
            "grazing_angle_deg": math.degrees(psi), "gamma_mag": abs(g),
            "gamma_phase_deg": math.degrees(cmath.phase(g)), "ground": ground, "pol": pol}


def path_loss(model, d_m, f_hz, ht_m=None, hr_m=None, ground="average", pol="v"):
    if model == "fspl":
        return fspl(d_m, f_hz)["fspl_db"]
    if model == "tworay":
        if ht_m is None or hr_m is None:
            raise ValueError("two-ray needs both antenna heights")
        return two_ray_ground(d_m, f_hz, ht_m, hr_m, ground, pol)["path_loss_db"]
    raise ValueError("model must be fspl or tworay")


def compare_models(f_hz, d_m, ht_m, hr_m, ground="average", pol="v"):
    tr = two_ray_ground(d_m, f_hz, ht_m, hr_m, ground, pol)
    region = "beyond crossover (40 dB/decade)" if d_m > tr["crossover_m"] else \
        "inside crossover (lobing about free space)"
    return {**tr, "two_ray_minus_fspl_db": tr["path_loss_db"] - tr["fspl_db"], "region": region}


def max_range(allowed_loss_db, f_hz, model="fspl", ht_m=None, hr_m=None, ground="average",
              pol="v"):
    """Distance out to which path loss stays within allowed_loss_db without a gap.

    FSPL is solved in closed form. Two-ray has nulls, so it is scanned on a log grid (0.36 %
    steps; a null narrower than that can be missed). max_range_m is the continuous range up to
    the first failing sample; last_lobe_m is the farthest constructive lobe that closes again.
    """
    lam = C0 / f_hz
    if model == "fspl":
        return {"max_range_m": lam / (4 * math.pi) * 10 ** (allowed_loss_db / 20)}
    ratio = (SCAN_MAX_M / SCAN_MIN_M) ** (1 / (SCAN_POINTS - 1))
    continuous, ok_last, failed = 0.0, None, False
    for i in range(SCAN_POINTS):
        d = SCAN_MIN_M * ratio ** i
        if path_loss(model, d, f_hz, ht_m, hr_m, ground, pol) <= allowed_loss_db:
            ok_last = d
            if not failed:
                continuous = d
        else:
            failed = True
    out = {"max_range_m": continuous}
    if ok_last is not None and ok_last > continuous:
        out["last_lobe_m"] = ok_last
    if not failed:
        out["warning"] = f"link still closes at the {SCAN_MAX_M / 1e3:.0f} km scan limit"
    return out


# ---------- Fresnel clearance ----------

def clearance(f_hz, d_m, d1_m, h_tx_m, h_rx_m, h_obs_m, k=4 / 3, required_pct=60.0):
    """Clearance of a single obstacle. Heights share one datum (e.g. metres above sea level)."""
    if not 0 < d1_m < d_m:
        raise ValueError("obstacle distance must lie between the two ends")
    lam = C0 / f_hz
    d2 = d_m - d1_m
    los = h_tx_m + (h_rx_m - h_tx_m) * d1_m / d_m
    bulge = d1_m * d2 / (2 * k * EARTH_R_KM * 1e3)
    f1 = math.sqrt(lam * d1_m * d2 / d_m)
    clear = los - (h_obs_m + bulge)
    need = required_pct / 100 * f1
    v = -math.sqrt(2) * clear / f1
    return {"los_height_m": los, "earth_bulge_m": bulge, "fresnel_f1_m": f1,
            "clearance_m": clear, "clearance_pct_f1": 100 * clear / f1,
            "required_m": need, "meets_requirement": clear >= need,
            "raise_both_ends_by_m": max(0.0, need - clear), "fresnel_v": v,
            "knife_edge_loss_db": knife_edge_loss(v), "k_factor": k}


# ---------- link budget ----------

def budget(f_hz, d_m, p_tx_dbm, g_tx=0.0, g_rx=0.0, l_tx=0.0, l_rx=0.0, l_misc=0.0,
           model="fspl", ht_m=None, hr_m=None, ground="average", pol="v", pl_db=None,
           sens_dbm=None, bw_hz=None, nf_db=None, snr_db=None, reliability=None,
           fade_db=None, k=4 / 3):
    e = eirp(p_tx_dbm, g_tx, l_tx)["eirp_dBm"]
    pl = pl_db if pl_db is not None else path_loss(model, d_m, f_hz, ht_m, hr_m, ground, pol)
    prx = e - pl - l_misc + g_rx - l_rx
    out = {"eirp_dBm": e, "path_loss_model": "given" if pl_db is not None else model,
           "path_loss_db": pl, "misc_loss_db": l_misc, "received_dBm": prx}
    if bw_hz and nf_db is not None:
        floor = noise_floor(bw_hz, nf_db)["noise_floor_dBm"]
        out.update({"noise_floor_dBm": floor, "snr_db": prx - floor})
    if sens_dbm is None:
        if out.get("noise_floor_dBm") is None or snr_db is None:
            raise ValueError("give --sens, or --bw, --nf and --snr to compute it")
        sens_dbm = out["noise_floor_dBm"] + snr_db
        out["sensitivity_source"] = "kTB + NF + SNR"
    out["sensitivity_dBm"] = sens_dbm
    need = 0.0
    if fade_db is not None or reliability is not None:
        fm = fade_margin(reliability, fade_db)
        need = fm["fade_margin_db"]
        out["required_fade_margin_db"] = need
    out["link_margin_db"] = prx - sens_dbm
    out["excess_margin_db"] = prx - sens_dbm - need
    out["closes"] = out["excess_margin_db"] >= 0
    if pl_db is None:
        allowed = e - l_misc + g_rx - l_rx - sens_dbm - need
        rng = max_range(allowed, f_hz, model, ht_m, hr_m, ground, pol)
        out["max_range_km"] = rng["max_range_m"] / 1e3
        if "last_lobe_m" in rng:
            out["last_lobe_km"] = rng["last_lobe_m"] / 1e3
        if "warning" in rng:
            out["scan_warning"] = rng["warning"]
    if ht_m is not None and hr_m is not None:
        hz = radio_horizon(ht_m, hr_m, k)["max_los_km"]
        out["radio_horizon_km"] = hz
        if d_m / 1e3 > hz:
            out["warning"] = "distance is beyond the radio horizon: link is not line of sight"
        elif out.get("max_range_km", 0) > hz:
            out["range_note"] = "max range is horizon-limited"
    return out


# ---------- detection range ----------

def albersheim_snr(pd, pfa, n=1):
    """Single-pulse-equivalent SNR (dB) per pulse for a steady target, N noncoherent pulses."""
    a = math.log(0.62 / pfa)
    b = math.log(pd / (1 - pd))
    return -5 * math.log10(n) + (6.2 + 4.54 / math.sqrt(n + 0.44)) * math.log10(
        a + 0.12 * a * b + 1.7 * b)


def swerling1_snr(pd, pfa):
    """Exact single-pulse SNR (dB), Swerling 1 (Rayleigh) target: Pd = Pfa^(1/(1+SNR))."""
    return 10 * math.log10(math.log(pfa) / math.log(pd) - 1)


def required_snr(pd, pfa, n=1, target="steady"):
    if not (0 < pd < 1 and 0 < pfa < 1 and pd > pfa):
        raise ValueError("need 0 < Pfa < Pd < 1")
    warnings = []
    if target == "steady":
        if not (1e-7 <= pfa <= 1e-3 and 0.1 <= pd <= 0.9 and 1 <= n <= 8096):
            warnings.append("Albersheim is fitted for Pfa 1e-7..1e-3, Pd 0.1..0.9, N 1..8096")
        return albersheim_snr(pd, pfa, n), "Albersheim (Swerling 0)", warnings
    if target == "swerling1":
        if n != 1:
            raise ValueError("swerling1 uses the exact single-pulse form; use --pulses for "
                             "coherent gain instead of --noncoh")
        return swerling1_snr(pd, pfa), "Swerling 1 exact, single pulse", warnings
    raise ValueError("target must be steady or swerling1")


def detect_radar(pt_w, g_dbi, f_hz, rcs_list, bw_hz, nf_db, losses_db=0.0, pd=0.9, pfa=1e-6,
                 n_coh=1, n_noncoh=1, target="steady", h_radar_m=None, h_target_m=None,
                 k=4 / 3):
    """Free-space radar detection range per RCS, capped by the radar horizon."""
    if n_coh < 1 or n_noncoh < 1:
        raise ValueError("pulse counts must be >= 1")
    if any(r <= 0 for r in rcs_list):
        raise ValueError("RCS must be > 0 m^2")
    snr, basis, warnings = required_snr(pd, pfa, n_noncoh, target)
    hz = radio_horizon(h_radar_m, h_target_m, k)["max_los_km"] if (
        h_radar_m is not None and h_target_m is not None) else None
    rows = []
    for rcs in rcs_list:
        r = radar(pt_w, g_dbi, f_hz, rcs, bw_hz, nf_db, snr, losses_db, n_pulses=n_coh)
        row = {"rcs_m2": rcs, "rcs_dBsm": 10 * math.log10(rcs),
               "free_space_range_km": r["max_range_km"]}
        if hz is not None:
            row["detection_range_km"] = min(r["max_range_km"], hz)
            row["horizon_limited"] = r["max_range_km"] > hz
        rows.append(row)
    out = {"required_snr_db": snr, "detection_model": basis, "pd": pd, "pfa": pfa,
           "coherent_pulses": n_coh, "noncoherent_pulses": n_noncoh, "ranges": rows}
    if hz is not None:
        out["radar_horizon_km"] = hz
    warnings.append("free-space estimate: ground clutter, multipath and terrain masking "
                    "usually shorten it for low-flying targets")
    out["warnings"] = warnings
    return out


def detect_rf(emitter_eirp_dbm, f_hz, bw_hz, nf_db, snr_db=10.0, g_sensor=0.0, l_sensor=0.0,
              l_misc=0.0, h_sensor_m=None, h_target_m=None, ground="average", pol="v",
              k=4 / 3):
    """Range at which a passive receiver hears an emitter (control link, video, telemetry)."""
    s = sensitivity(bw_hz, nf_db, snr_db)
    allowed = emitter_eirp_dbm + g_sensor - l_sensor - l_misc - s["sensitivity_dBm"]
    out = {**s, "allowed_path_loss_db": allowed,
           "free_space_range_km": max_range(allowed, f_hz)["max_range_m"] / 1e3}
    if h_sensor_m is not None and h_target_m is not None:
        tr = max_range(allowed, f_hz, "tworay", h_sensor_m, h_target_m, ground, pol)
        hz = radio_horizon(h_sensor_m, h_target_m, k)["max_los_km"]
        out.update({"two_ray_range_km": tr["max_range_m"] / 1e3, "radio_horizon_km": hz,
                    "detection_range_km": min(tr["max_range_m"] / 1e3, hz)})
        if "last_lobe_m" in tr:
            out["last_lobe_km"] = tr["last_lobe_m"] / 1e3
    out["note"] = ("emitter EIRP and duty cycle vary by model and mode; a hopping or bursty "
                   "signal needs the sensor bandwidth and dwell to match it")
    return out


# ---------- CLI ----------

def _ground_args(a):
    a.add_argument("--ground", default="average", choices=list(GROUNDS))
    a.add_argument("--pol", default="v", choices=["v", "h"])


def register(sp):
    a = sp.add_parser("eirp", help="EIRP / ERP from TX power, gain and feeder loss")
    a.add_argument("ptx", type=float, help="TX power dBm")
    a.add_argument("--gtx", type=float, default=0.0)
    a.add_argument("--ltx", type=float, default=0.0)
    a.set_defaults(func=lambda x: eirp(x.ptx, x.gtx, x.ltx))

    a = sp.add_parser("sens", help="receive sensitivity = kTB + NF + SNR")
    a.add_argument("bw", type=freq)
    a.add_argument("--nf", type=float, required=True)
    a.add_argument("--snr", type=float, required=True)
    a.set_defaults(func=lambda x: sensitivity(x.bw, x.nf, x.snr))

    a = sp.add_parser("fademargin", help="Rayleigh fade margin <-> reliability")
    a.add_argument("--reliability", type=float, help="percent, e.g. 99.9")
    a.add_argument("--margin", type=float, help="dB")
    a.set_defaults(func=lambda x: fade_margin(
        None if x.reliability is None else x.reliability / 100, x.margin))

    a = sp.add_parser("pathloss", help="free space vs two-ray over real ground")
    a.add_argument("f", type=freq)
    a.add_argument("d", type=dist)
    a.add_argument("ht", type=dist)
    a.add_argument("hr", type=dist)
    _ground_args(a)
    a.set_defaults(func=lambda x: compare_models(x.f, x.d, x.ht, x.hr, x.ground, x.pol))

    a = sp.add_parser("clearance", help="Fresnel clearance of one obstacle (common datum)")
    a.add_argument("f", type=freq)
    a.add_argument("d", type=dist, help="path length")
    a.add_argument("d1", type=dist, help="obstacle distance from TX")
    a.add_argument("--htx", type=dist, required=True, help="TX antenna height on the datum")
    a.add_argument("--hrx", type=dist, required=True)
    a.add_argument("--hobs", type=dist, required=True, help="obstacle top on the datum")
    a.add_argument("--k", type=float, default=4 / 3)
    a.add_argument("--pct", type=float, default=60.0, help="required %% of F1")
    a.set_defaults(func=lambda x: clearance(x.f, x.d, x.d1, x.htx, x.hrx, x.hobs, x.k, x.pct))

    a = sp.add_parser("budget", help="link budget with fade margin, max range and horizon")
    a.add_argument("--f", type=freq, required=True)
    a.add_argument("--d", type=dist, required=True)
    a.add_argument("--ptx", type=float, required=True, help="dBm")
    for name in ("gtx", "grx", "ltx", "lrx", "lmisc"):
        a.add_argument(f"--{name}", type=float, default=0.0)
    a.add_argument("--model", default="fspl", choices=["fspl", "tworay"])
    a.add_argument("--ht", type=dist)
    a.add_argument("--hr", type=dist)
    _ground_args(a)
    a.add_argument("--pl", type=float, help="use this path loss instead of a model")
    a.add_argument("--sens", type=float, help="dBm; or give --bw --nf --snr")
    a.add_argument("--bw", type=freq)
    a.add_argument("--nf", type=float)
    a.add_argument("--snr", type=float)
    a.add_argument("--reliability", type=float, help="Rayleigh, percent")
    a.add_argument("--fade", type=float, help="required fade margin dB")
    a.add_argument("--k", type=float, default=4 / 3)
    a.set_defaults(func=lambda x: budget(
        x.f, x.d, x.ptx, x.gtx, x.grx, x.ltx, x.lrx, x.lmisc, x.model, x.ht, x.hr, x.ground,
        x.pol, x.pl, x.sens, x.bw, x.nf, x.snr,
        None if x.reliability is None else x.reliability / 100, x.fade, x.k))

    a = sp.add_parser("detect-radar", help="radar detection range vs RCS (Pd/Pfa based)")
    a.add_argument("--pt", type=qty, required=True, help="peak power W")
    a.add_argument("--g", type=float, required=True, help="antenna gain dBi")
    a.add_argument("--f", type=freq, required=True)
    a.add_argument("--rcs", type=float, nargs="+", required=True, help="m^2, one or more")
    a.add_argument("--bw", type=freq, required=True)
    a.add_argument("--nf", type=float, required=True)
    a.add_argument("--losses", type=float, default=0.0)
    a.add_argument("--pd", type=float, default=0.9)
    a.add_argument("--pfa", type=float, default=1e-6)
    a.add_argument("--pulses", type=int, default=1, help="coherently integrated pulses")
    a.add_argument("--noncoh", type=int, default=1, help="noncoherent pulses (steady only)")
    a.add_argument("--target", default="steady", choices=["steady", "swerling1"])
    a.add_argument("--hradar", type=dist)
    a.add_argument("--htarget", type=dist)
    a.add_argument("--k", type=float, default=4 / 3)
    a.set_defaults(func=lambda x: detect_radar(
        x.pt, x.g, x.f, x.rcs, x.bw, x.nf, x.losses, x.pd, x.pfa, x.pulses, x.noncoh,
        x.target, x.hradar, x.htarget, x.k))

    a = sp.add_parser("detect-rf", help="passive RF detection range of an emitter")
    a.add_argument("--eirp", type=float, required=True, help="emitter EIRP dBm")
    a.add_argument("--f", type=freq, required=True)
    a.add_argument("--bw", type=freq, required=True, help="sensor detection bandwidth")
    a.add_argument("--nf", type=float, required=True)
    a.add_argument("--snr", type=float, default=10.0)
    a.add_argument("--g", type=float, default=0.0, help="sensor antenna gain dBi")
    a.add_argument("--l", type=float, default=0.0, help="sensor feeder loss dB")
    a.add_argument("--lmisc", type=float, default=0.0)
    a.add_argument("--hsensor", type=dist)
    a.add_argument("--htarget", type=dist)
    _ground_args(a)
    a.add_argument("--k", type=float, default=4 / 3)
    a.set_defaults(func=lambda x: detect_rf(
        x.eirp, x.f, x.bw, x.nf, x.snr, x.g, x.l, x.lmisc, x.hsensor, x.htarget, x.ground,
        x.pol, x.k))
