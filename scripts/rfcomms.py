"""Digital comms, satellite links, radar, polarization, phase noise and mixer frequency planning."""
import math

from rfargs import dist, freq, qty
from rfcore import C0, K_BOLTZMANN, T0

BOLTZMANN_DB = 10 * math.log10(K_BOLTZMANN)  # -228.6 dBW/K/Hz
WGS84_A = 6_378_137.0
WGS84_F = 1 / 298.257223563
GEO_ALT_M = 35_786_000.0
MU_EARTH = 3.986004418e14  # m^3/s^2
EARTH_R_M = 6_371_000.0


# ---------- digital modulation ----------

def qfunc(x):
    return 0.5 * math.erfc(x / math.sqrt(2))


def ber(mod, ebn0_db):
    """Bit error rate on AWGN. M-QAM/M-PSK use Gray-coded nearest-neighbour approximations."""
    g = 10 ** (ebn0_db / 10)
    mod = mod.lower()
    if mod in ("bpsk", "qpsk", "oqpsk"):
        return qfunc(math.sqrt(2 * g))
    if mod == "dbpsk":
        return 0.5 * math.exp(-g)
    if mod == "bfsk":  # coherent orthogonal
        return qfunc(math.sqrt(g))
    if mod in ("ncfsk", "bfsk-nc"):
        return 0.5 * math.exp(-g / 2)
    if mod == "ook":  # coherent on-off keying, Eb = average
        return qfunc(math.sqrt(g))
    m = _order(mod)
    k = math.log2(m)
    if mod.endswith("psk"):
        return 2 / k * qfunc(math.sqrt(2 * k * g) * math.sin(math.pi / m))
    if mod.endswith("qam"):
        return 4 / k * (1 - 1 / math.sqrt(m)) * qfunc(math.sqrt(3 * k * g / (m - 1)))
    raise ValueError("mod: bpsk qpsk dbpsk bfsk ncfsk ook 8psk 16psk 16qam 64qam 256qam 1024qam")


def _order(mod):
    digits = "".join(ch for ch in mod if ch.isdigit())
    if not digits:
        raise ValueError(f"unknown modulation '{mod}'")
    m = int(digits)
    if m < 4 or m & (m - 1):
        raise ValueError("order must be a power of two >= 4")
    return m


def bits_per_symbol(mod):
    mod = mod.lower()
    if mod in ("bpsk", "dbpsk", "bfsk", "ncfsk", "bfsk-nc", "ook"):
        return 1
    if mod in ("qpsk", "oqpsk"):
        return 2
    return int(math.log2(_order(mod)))


def required_ebn0(mod, target_ber):
    lo, hi = -10.0, 60.0
    if ber(mod, hi) > target_ber:
        raise ValueError("target BER not reachable below 60 dB")
    for _ in range(100):
        mid = (lo + hi) / 2
        if ber(mod, mid) > target_ber:
            lo = mid
        else:
            hi = mid
    return hi


def modem(mod, ebn0_db=None, target_ber=None, rb=None, rolloff=0.35, code_rate=1.0):
    k = bits_per_symbol(mod)
    out = {"modulation": mod, "bits_per_symbol": k, "code_rate": code_rate}
    if target_ber is not None:
        ebn0_db = required_ebn0(mod, target_ber)
        out["required_EbN0_dB"] = ebn0_db
    if ebn0_db is not None:
        out["BER"] = ber(mod, ebn0_db)
        out["EbN0_dB"] = ebn0_db
    if rb:
        rs = rb / (k * code_rate)
        bw = rs * (1 + rolloff)
        out.update({"symbol_rate_Bd": rs, "occupied_bw_hz": bw,
                    "spectral_eff_bps_hz": rb / bw})
        if ebn0_db is not None:
            out["required_SNR_dB_in_bw"] = ebn0_db + 10 * math.log10(rb / bw)
    return out


def shannon(bw_hz, snr_db=None, rate_bps=None):
    out = {"bandwidth_hz": bw_hz, "shannon_limit_EbN0_dB": 10 * math.log10(math.log(2))}
    if snr_db is not None:
        c = bw_hz * math.log2(1 + 10 ** (snr_db / 10))
        out.update({"capacity_bps": c, "spectral_eff_bps_hz": c / bw_hz})
    if rate_bps is not None:
        eta = rate_bps / bw_hz
        snr_min = 2 ** eta - 1
        out.update({"min_SNR_dB": 10 * math.log10(snr_min),
                    "min_EbN0_dB": 10 * math.log10(snr_min / eta)})
    return out


# ---------- satellite ----------

def _ecef(lat, lon, alt):
    la, lo = math.radians(lat), math.radians(lon)
    e2 = WGS84_F * (2 - WGS84_F)
    n = WGS84_A / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return ((n + alt) * math.cos(la) * math.cos(lo), (n + alt) * math.cos(la) * math.sin(lo),
            (n * (1 - e2) + alt) * math.sin(la))


def look_angles(lat, lon, alt_m, sat_lat, sat_lon, sat_alt_m=GEO_ALT_M):
    sx, sy, sz = _ecef(sat_lat, sat_lon, sat_alt_m)
    gx, gy, gz = _ecef(lat, lon, alt_m)
    dx, dy, dz = sx - gx, sy - gy, sz - gz
    la, lo = math.radians(lat), math.radians(lon)
    e = -math.sin(lo) * dx + math.cos(lo) * dy
    n = (-math.sin(la) * math.cos(lo) * dx - math.sin(la) * math.sin(lo) * dy
         + math.cos(la) * dz)
    u = math.cos(la) * math.cos(lo) * dx + math.cos(la) * math.sin(lo) * dy + math.sin(la) * dz
    rng = math.sqrt(dx * dx + dy * dy + dz * dz)
    out = {"azimuth_deg": math.degrees(math.atan2(e, n)) % 360,
           "elevation_deg": math.degrees(math.asin(u / rng)), "slant_range_km": rng / 1e3,
           "one_way_delay_ms": rng / C0 * 1e3}
    if out["elevation_deg"] < 0:
        out["warning"] = "satellite is below the horizon"
    return out


def system_temp(t_ant_k, te_rx_k, feed_loss_db=0.0, t_phys_k=T0):
    lf = 10 ** (feed_loss_db / 10)
    return t_ant_k / lf + t_phys_k * (1 - 1 / lf) + te_rx_k


def sat_link(eirp_dbw, f_hz, range_m, gt_dbk=None, g_rx_dbi=None, tsys_k=None, losses_db=0.0,
             bw_hz=None, rb=None):
    if gt_dbk is None:
        if g_rx_dbi is None or tsys_k is None:
            raise ValueError("give --gt, or --grx with --tsys")
        gt_dbk = g_rx_dbi - 10 * math.log10(tsys_k)
    fspl = 20 * math.log10(4 * math.pi * range_m * f_hz / C0)
    cn0 = eirp_dbw - fspl - losses_db + gt_dbk - BOLTZMANN_DB
    out = {"fspl_db": fspl, "G_over_T_dBK": gt_dbk, "C_N0_dBHz": cn0}
    if bw_hz:
        out["C_N_dB"] = cn0 - 10 * math.log10(bw_hz)
    if rb:
        out["Eb_N0_dB"] = cn0 - 10 * math.log10(rb)
    return out


def orbit(alt_m, f_hz=None, min_el_deg=10.0):
    r = EARTH_R_M + alt_m
    v = math.sqrt(MU_EARTH / r)
    el = math.radians(min_el_deg)
    rs = EARTH_R_M * math.sin(el)
    slant = -rs + math.sqrt(rs ** 2 + alt_m ** 2 + 2 * EARTH_R_M * alt_m)
    # range-rate at elevation e for an overhead pass (non-rotating earth): v Re cos(e) / r
    vr = v * EARTH_R_M * math.cos(el) / r
    out = {"velocity_m_s": v, "period_min": 2 * math.pi * r / v / 60,
           "slant_range_at_min_el_km": slant / 1e3, "range_rate_at_min_el_m_s": vr}
    if f_hz:
        out["max_doppler_hz"] = vr * f_hz / C0
        out["max_doppler_rate_hz_s_overhead"] = f_hz / C0 * v ** 2 * EARTH_R_M / (r * alt_m)
    return out


# ---------- polarization ----------

def polarization_loss(ar1_db, ar2_db, tilt_deg=0.0, same_sense=True):
    """PLF between two elliptical antennas (axial ratio in dB, 0 = circular, >=40 ~ linear)."""
    def ratio(ar_db):
        return min(10 ** (ar_db / 20), 1e6)

    r1, r2 = ratio(ar1_db), ratio(ar2_db) * (1 if same_sense else -1)
    num = 4 * r1 * r2 + (1 - r1 ** 2) * (1 - r2 ** 2) * math.cos(2 * math.radians(tilt_deg))
    plf = 0.5 + num / (2 * (1 + r1 ** 2) * (1 + r2 ** 2))
    plf = max(plf, 1e-12)
    return {"PLF": plf, "polarization_loss_db": -10 * math.log10(plf)}


# ---------- radar ----------

def radar(pt_w, g_db, f_hz, rcs_m2, bw_hz, nf_db, snr_min_db=13.0, losses_db=0.0,
          prf_hz=None, pulse_s=None, n_pulses=1, range_m=None):
    lam = C0 / f_hz
    g = 10 ** (g_db / 10)
    l_tot = 10 ** ((losses_db + nf_db) / 10)
    snr_min = 10 ** (snr_min_db / 10) / n_pulses  # coherent integration gain
    num = pt_w * g ** 2 * lam ** 2 * rcs_m2
    den = (4 * math.pi) ** 3 * K_BOLTZMANN * T0 * bw_hz * l_tot
    out = {"max_range_km": (num / (den * snr_min)) ** 0.25 / 1e3, "lambda_m": lam,
           "integration_gain_db": 10 * math.log10(n_pulses)}
    if range_m:
        out["snr_at_range_db"] = 10 * math.log10(num / (den * range_m ** 4) * n_pulses)
    if pulse_s:
        out["range_resolution_m"] = C0 * pulse_s / 2
    if prf_hz:
        out.update({"max_unambiguous_range_km": C0 / (2 * prf_hz) / 1e3,
                    "max_unambiguous_velocity_m_s": lam * prf_hz / 4,
                    "first_blind_speed_m_s": lam * prf_hz / 2})
        if pulse_s:
            out["duty_cycle"] = pulse_s * prf_hz
            out["avg_power_w"] = pt_w * pulse_s * prf_hz
            out["min_range_m"] = C0 * pulse_s / 2
    return out


# ---------- phase noise ----------

def jitter(f0_hz, points, f_lo=None, f_hi=None):
    """RMS jitter from SSB phase noise points [(offset_hz, dBc/Hz)], power-law between points."""
    pts = sorted(points)
    if len(pts) < 2:
        raise ValueError("need at least two offset:dBc points")
    f_lo = f_lo or pts[0][0]
    f_hi = f_hi or pts[-1][0]
    total = 0.0
    for (fa, la), (fb, lb) in zip(pts, pts[1:]):
        a, b = max(fa, f_lo), min(fb, f_hi)
        if b <= a:
            continue
        slope = (lb - la) / 10 / math.log10(fb / fa)  # power-law exponent
        pa = 10 ** ((la + 10 * slope * math.log10(a / fa)) / 10)
        if abs(slope + 1) < 1e-9:
            total += pa * a * math.log(b / a)
        else:
            total += pa * a / (slope + 1) * ((b / a) ** (slope + 1) - 1)
    phi = math.sqrt(2 * total)
    return {"integrated_dBc": 10 * math.log10(total * 2), "rms_phase_rad": phi,
            "rms_phase_deg": math.degrees(phi), "rms_jitter_s": phi / (2 * math.pi * f0_hz),
            "evm_limit_pct": 100 * phi, "band_hz": [f_lo, f_hi]}


def reciprocal_mixing(blocker_dbm, pn_dbc_hz, ch_bw_hz, sensitivity_dbm=None, snr_db=None):
    noise = blocker_dbm + pn_dbc_hz + 10 * math.log10(ch_bw_hz)
    out = {"reciprocal_mixing_noise_dBm": noise}
    if sensitivity_dbm is not None and snr_db is not None:
        out["max_blocker_dBm"] = sensitivity_dbm - snr_db - pn_dbc_hz - 10 * math.log10(ch_bw_hz)
    return out


# ---------- mixer frequency planning ----------

def mixer_plan(rf_lo, rf_hi, if_hz, side="low", order=5, steps=101):
    """Every m*LO, n*RF product (m+n <= order) that lands on the IF, as an input range.

    An input range overlapping the RF band is an in-band spur a preselector cannot remove.
    """
    sign = -1 if side == "low" else 1
    spans = {}
    for i in range(steps):
        rf = rf_lo + (rf_hi - rf_lo) * i / (steps - 1)
        lo = rf + sign * if_hz
        for m in range(0, order + 1):
            for n in range(1, order + 1 - m):
                for s in (1, -1):
                    f_in = (m * lo + s * if_hz) / n
                    if f_in <= 0:
                        continue
                    key = (m, n, s)
                    lo_f, hi_f = spans.get(key, (math.inf, -math.inf))
                    spans[key] = (min(lo_f, f_in), max(hi_f, f_in))
    wanted_s = 1 if side == "low" else -1  # low side: RF = LO + IF
    rows = []
    for (m, n, s), (a, b) in spans.items():
        if (m, n, s) == (1, 1, wanted_s):
            continue
        kind = "image" if (m, n) == (1, 1) else ("IF feedthrough" if m == 0 else "spur")
        rows.append({"m_LO": m, "n_RF": n, "kind": kind, "input_lo_hz": a, "input_hi_hz": b,
                     "in_band": a <= rf_hi and b >= rf_lo})
    rows.sort(key=lambda r: (not r["in_band"], r["m_LO"] + r["n_RF"]))
    lo_lo = rf_lo + sign * if_hz
    lo_hi = rf_hi + sign * if_hz
    return {"lo_range_hz": [min(lo_lo, lo_hi), max(lo_lo, lo_hi)],
            "image_range_hz": [rf_lo + 2 * sign * if_hz, rf_hi + 2 * sign * if_hz],
            "in_band_spurs": sum(r["in_band"] for r in rows), "products": rows}


# ---------- CLI ----------

def _pairs(specs):
    out = []
    for s in specs:
        a, b = s.split(":")
        out.append((freq(a), float(b.replace("~", "-"))))
    return out


def register(sp):
    a = sp.add_parser("ber", help="BER / required Eb/N0 / occupied bandwidth for a modulation")
    a.add_argument("mod")
    a.add_argument("--ebn0", type=float)
    a.add_argument("--target", type=float, help="target BER, e.g. 1e-6")
    a.add_argument("--rb", type=freq, help="bit rate (b/s, suffixes ok)")
    a.add_argument("--rolloff", type=float, default=0.35)
    a.add_argument("--rate", type=float, default=1.0, help="FEC code rate")
    a.set_defaults(func=lambda x: modem(x.mod, x.ebn0, x.target, x.rb, x.rolloff, x.rate))

    a = sp.add_parser("shannon", help="channel capacity / minimum SNR for a rate")
    a.add_argument("bw", type=freq)
    a.add_argument("--snr", type=float)
    a.add_argument("--rate", type=freq)
    a.set_defaults(func=lambda x: shannon(x.bw, x.snr, x.rate))

    a = sp.add_parser("look", help="satellite azimuth/elevation/range from a ground site")
    a.add_argument("lat", type=float)
    a.add_argument("lon", type=float)
    a.add_argument("--alt", type=dist, default=0.0)
    a.add_argument("--sat-lon", type=float, required=True)
    a.add_argument("--sat-lat", type=float, default=0.0)
    a.add_argument("--sat-alt", type=dist, default=GEO_ALT_M)
    a.set_defaults(func=lambda x: look_angles(x.lat, x.lon, x.alt, x.sat_lat, x.sat_lon,
                                              x.sat_alt))

    a = sp.add_parser("satlink", help="C/N0, C/N, Eb/N0 for a satellite link")
    a.add_argument("--eirp", type=float, required=True, help="dBW")
    a.add_argument("--f", type=freq, required=True)
    a.add_argument("--range", type=dist, required=True, dest="rng")
    a.add_argument("--gt", type=float, help="G/T dB/K")
    a.add_argument("--grx", type=float)
    a.add_argument("--tsys", type=float, help="system temperature K")
    a.add_argument("--losses", type=float, default=0.0, help="atmos + pointing + pol dB")
    a.add_argument("--bw", type=freq)
    a.add_argument("--rb", type=freq)
    a.set_defaults(func=lambda x: sat_link(x.eirp, x.f, x.rng, x.gt, x.grx, x.tsys, x.losses,
                                           x.bw, x.rb))

    a = sp.add_parser("tsys", help="system noise temperature incl. feed loss")
    a.add_argument("tant", type=float)
    a.add_argument("terx", type=float)
    a.add_argument("--feed-loss", type=float, default=0.0)
    a.set_defaults(func=lambda x: {"Tsys_K": system_temp(x.tant, x.terx, x.feed_loss)})

    a = sp.add_parser("orbit", help="circular orbit velocity, period, pass range, max Doppler")
    a.add_argument("alt", type=dist)
    a.add_argument("--f", type=freq)
    a.add_argument("--min-el", type=float, default=10.0)
    a.set_defaults(func=lambda x: orbit(x.alt, x.f, x.min_el))

    a = sp.add_parser("polloss", help="polarization mismatch loss from axial ratios")
    a.add_argument("ar1", type=float, help="axial ratio dB (0 circular, 40+ linear)")
    a.add_argument("ar2", type=float)
    a.add_argument("--tilt", type=float, default=0.0, help="angle between major axes, deg")
    a.add_argument("--opposite", action="store_true", help="opposite rotation sense")
    a.set_defaults(func=lambda x: polarization_loss(x.ar1, x.ar2, x.tilt, not x.opposite))

    a = sp.add_parser("radar", help="radar range equation, ambiguities, resolution")
    a.add_argument("--pt", type=qty, required=True, help="peak power W (1M ok)")
    a.add_argument("--g", type=float, required=True, help="antenna gain dBi")
    a.add_argument("--f", type=freq, required=True)
    a.add_argument("--rcs", type=float, required=True, help="m^2")
    a.add_argument("--bw", type=freq, required=True)
    a.add_argument("--nf", type=float, required=True)
    a.add_argument("--snr", type=float, default=13.0, help="required SNR dB")
    a.add_argument("--losses", type=float, default=0.0)
    a.add_argument("--prf", type=freq)
    a.add_argument("--pulse", type=lambda t: qty(t, "s"))
    a.add_argument("--pulses", type=int, default=1, help="coherently integrated pulses")
    a.add_argument("--range", type=dist, dest="rng")
    a.set_defaults(func=lambda x: radar(x.pt, x.g, x.f, x.rcs, x.bw, x.nf, x.snr, x.losses,
                                        x.prf, x.pulse, x.pulses, x.rng))

    a = sp.add_parser("jitter", help="RMS jitter from phase-noise points offset:dBc")
    a.add_argument("f0", type=freq)
    a.add_argument("points", nargs="+", help="e.g. 1k:-80 10k:-90 100k:-110 1M:-130")
    a.add_argument("--from", type=freq, dest="f_lo")
    a.add_argument("--to", type=freq, dest="f_hi")
    a.set_defaults(func=lambda x: jitter(x.f0, _pairs(x.points), x.f_lo, x.f_hi))

    a = sp.add_parser("recipmix", help="reciprocal mixing noise from a blocker")
    a.add_argument("blocker", type=float, help="dBm")
    a.add_argument("pn", type=float, help="LO phase noise at blocker offset, dBc/Hz")
    a.add_argument("bw", type=freq)
    a.add_argument("--sens", type=float)
    a.add_argument("--snr", type=float)
    a.set_defaults(func=lambda x: reciprocal_mixing(x.blocker, x.pn, x.bw, x.sens, x.snr))

    a = sp.add_parser("mixer", help="LO/image/spur plan for a tuned band")
    a.add_argument("rf_lo", type=freq)
    a.add_argument("rf_hi", type=freq)
    a.add_argument("if_", type=freq, metavar="IF")
    a.add_argument("--side", choices=["low", "high"], default="low", help="LO below/above RF")
    a.add_argument("--order", type=int, default=5)
    a.set_defaults(func=lambda x: mixer_plan(x.rf_lo, x.rf_hi, x.if_, x.side, x.order))
