"""Propagation, link budgets, path geometry, field strength, RF exposure, aviation channels."""
import math

from rfcore import C0, dbm_to_w, noise_floor

EARTH_R_KM = 6371.0


def fspl(d_m, f_hz):
    """Free-space path loss (isotropic antennas), Friis: (4 pi d / lambda)^2."""
    if d_m <= 0 or f_hz <= 0:
        raise ValueError("distance and frequency must be > 0")
    lam = C0 / f_hz
    loss = 20 * math.log10(4 * math.pi * d_m / lam)
    far_field_note = "d is within ~1 wavelength: near field, FSPL invalid" if d_m < lam else None
    out = {"fspl_db": loss, "lambda_m": lam}
    if far_field_note:
        out["warning"] = far_field_note
    return out


def fspl_distance(loss_db, f_hz):
    lam = C0 / f_hz
    return {"distance_m": lam / (4 * math.pi) * 10 ** (loss_db / 20)}


def link_budget(p_tx_dbm, g_tx_dbi, g_rx_dbi, f_hz, d_m, tx_loss_db=0.0, rx_loss_db=0.0,
                misc_loss_db=0.0, rx_sens_dbm=None, bw_hz=None, nf_db=None, path_loss_db=None):
    pl = path_loss_db if path_loss_db is not None else fspl(d_m, f_hz)["fspl_db"]
    eirp = p_tx_dbm - tx_loss_db + g_tx_dbi
    prx = eirp - pl - misc_loss_db + g_rx_dbi - rx_loss_db
    out = {"eirp_dBm": eirp, "erp_dBm": eirp - 2.15, "path_loss_db": pl,
           "received_dBm": prx, "received_W": dbm_to_w(prx)}
    if bw_hz and nf_db is not None:
        floor = noise_floor(bw_hz, nf_db)["noise_floor_dBm"]
        out["noise_floor_dBm"] = floor
        out["snr_db"] = prx - floor
    if rx_sens_dbm is not None:
        margin = prx - rx_sens_dbm
        out["fade_margin_db"] = margin
        lam = C0 / f_hz
        # distance at which margin reaches zero under free space
        out["max_range_free_space_m"] = (lam / (4 * math.pi)) * 10 ** (
            (pl + margin) / 20) if path_loss_db is None else None
        out["range_note"] = "free-space range ignores the radio horizon; check `horizon`"
    return out


def fresnel(d1_m, d2_m, f_hz, zone=1, k=4 / 3):
    """Fresnel radius at a point plus earth bulge and recommended clearance."""
    lam = C0 / f_hz
    d = d1_m + d2_m
    r = math.sqrt(zone * lam * d1_m * d2_m / d)
    bulge = d1_m * d2_m / (2 * k * EARTH_R_KM * 1e3)
    return {"fresnel_radius_m": r, "clear_60pct_m": 0.6 * r, "earth_bulge_m": bulge,
            "clearance_needed_above_obstacle_m": 0.6 * r + bulge, "k_factor": k}


def radio_horizon(h1_m, h2_m=0.0, k=4 / 3):
    re = k * EARTH_R_KM * 1e3
    d1 = math.sqrt(2 * re * h1_m + h1_m ** 2)
    d2 = math.sqrt(2 * re * h2_m + h2_m ** 2)
    return {"horizon_tx_km": d1 / 1e3, "horizon_rx_km": d2 / 1e3,
            "max_los_km": (d1 + d2) / 1e3, "k_factor": k}


def two_ray(d_m, f_hz, ht_m, hr_m):
    """Flat-earth two-ray ground reflection; exact form with reflection coeff -1."""
    lam = C0 / f_hz
    d_direct = math.sqrt(d_m ** 2 + (ht_m - hr_m) ** 2)
    d_refl = math.sqrt(d_m ** 2 + (ht_m + hr_m) ** 2)
    phase = 2 * math.pi * (d_refl - d_direct) / lam
    field = abs(1 - complex(math.cos(phase), -math.sin(phase)))
    exact = fspl(d_direct, f_hz)["fspl_db"] - 20 * math.log10(max(field, 1e-12))
    crossover = 4 * math.pi * ht_m * hr_m / lam
    asym = 40 * math.log10(d_m) - 20 * math.log10(ht_m * hr_m)
    return {"two_ray_exact_db": exact, "two_ray_far_db": asym, "crossover_m": crossover,
            "fspl_db": fspl(d_m, f_hz)["fspl_db"],
            "note": "far-field 40 dB/decade valid beyond crossover"}


def hata(f_mhz, d_km, hb_m, hm_m, env="urban", city="medium"):
    """Okumura-Hata; COST-231 extension used automatically for 1500-2000 MHz."""
    warnings = []
    if not 150 <= f_mhz <= 2000:
        warnings.append("f outside 150-2000 MHz: model invalid")
    if not 1 <= d_km <= 20:
        warnings.append("d outside 1-20 km")
    if not 30 <= hb_m <= 200:
        warnings.append("base height outside 30-200 m")
    if not 1 <= hm_m <= 10:
        warnings.append("mobile height outside 1-10 m")
    lf, lhb = math.log10(f_mhz), math.log10(hb_m)
    if city == "large":
        a = (3.2 * math.log10(11.75 * hm_m) ** 2 - 4.97 if f_mhz >= 300
             else 8.29 * math.log10(1.54 * hm_m) ** 2 - 1.1)
    else:
        a = (1.1 * lf - 0.7) * hm_m - (1.56 * lf - 0.8)
    if f_mhz > 1500:
        cm = 3.0 if city == "large" else 0.0
        loss = 46.3 + 33.9 * lf - 13.82 * lhb - a + (44.9 - 6.55 * lhb) * math.log10(d_km) + cm
        model = "COST-231 Hata"
    else:
        loss = 69.55 + 26.16 * lf - 13.82 * lhb - a + (44.9 - 6.55 * lhb) * math.log10(d_km)
        model = "Okumura-Hata"
    if env == "suburban":
        loss -= 2 * math.log10(f_mhz / 28) ** 2 + 5.4
    elif env == "open":
        loss -= 4.78 * lf ** 2 - 18.33 * lf + 40.94
    out = {"model": model, "env": env, "path_loss_db": loss,
           "fspl_db": fspl(d_km * 1e3, f_mhz * 1e6)["fspl_db"]}
    if warnings:
        out["warnings"] = warnings
    return out


def field_strength(eirp_dbm=None, d_m=None, prx_dbm=None, f_mhz=None, g_dbi=0.0):
    """E-field from EIRP at distance, or from received power and antenna gain (50 ohm)."""
    out = {}
    if eirp_dbm is not None and d_m:
        e = math.sqrt(30 * dbm_to_w(eirp_dbm)) / d_m
        out.update({"E_V_per_m": e, "E_dBuV_per_m": 20 * math.log10(e * 1e6),
                    "power_density_W_m2": dbm_to_w(eirp_dbm) / (4 * math.pi * d_m ** 2)})
    if prx_dbm is not None and f_mhz:
        # E(dBuV/m) = P(dBm) + 20 log f(MHz) - G(dBi) + 77.2  (50 ohm system)
        out["E_from_prx_dBuV_per_m"] = prx_dbm + 20 * math.log10(f_mhz) - g_dbi + 77.2
        out["antenna_factor_dB_per_m"] = 20 * math.log10(f_mhz) - g_dbi - 29.79
    if not out:
        raise ValueError("give eirp+distance, or prx+frequency")
    return out


def doppler(v_mps, f_hz, angle_deg=0.0):
    fd = v_mps * f_hz * math.cos(math.radians(angle_deg)) / C0
    return {"doppler_shift_hz": fd, "coherence_time_s_approx": 0.423 / abs(fd) if fd else None}


def antenna(gain_dbi=None, aperture_m2=None, f_hz=None, diameter_m=None, efficiency=0.55):
    lam = C0 / f_hz
    out = {"lambda_m": lam}
    if diameter_m:
        g = efficiency * (math.pi * diameter_m / lam) ** 2
        out.update({"dish_gain_dBi": 10 * math.log10(g),
                    "beamwidth_3dB_deg": 70 * lam / diameter_m,
                    "far_field_m": 2 * diameter_m ** 2 / lam})
    if gain_dbi is not None:
        out["effective_aperture_m2"] = 10 ** (gain_dbi / 10) * lam ** 2 / (4 * math.pi)
        out["gain_dBd"] = gain_dbi - 2.15
    if aperture_m2:
        out["gain_from_aperture_dBi"] = 10 * math.log10(4 * math.pi * aperture_m2 / lam ** 2)
    return out


# FCC 47 CFR 1.1310 MPE, mW/cm^2, f in MHz
def _mpe_limit(f_mhz, occupational):
    if occupational:
        table = [(3, lambda f: 100), (30, lambda f: 900 / f ** 2), (300, lambda f: 1.0),
                 (1500, lambda f: f / 300), (100000, lambda f: 5.0)]
    else:
        table = [(1.34, lambda f: 100), (30, lambda f: 180 / f ** 2), (300, lambda f: 0.2),
                 (1500, lambda f: f / 1500), (100000, lambda f: 1.0)]
    if not 0.3 <= f_mhz <= 100000:
        raise ValueError("FCC MPE table covers 0.3 MHz - 100 GHz")
    for top, fn in table:
        if f_mhz <= top:
            return fn(f_mhz)
    raise ValueError("unreachable")


def mpe(eirp_w, f_mhz, d_m=None, occupational=False, ground_reflection=True):
    """FCC MPE screening. Ground reflection factor 2.56 per OET Bulletin 65."""
    limit = _mpe_limit(f_mhz, occupational)
    factor = 2.56 if ground_reflection else 1.0
    # S (mW/cm^2) = factor * EIRP(W) * 1000 / (4 pi (100 d)^2) ; solve d for S = limit
    safe_d = math.sqrt(factor * eirp_w * 1000 / (4 * math.pi * limit)) / 100
    out = {"limit_mW_cm2": limit, "class": "occupational" if occupational else "general public",
           "min_compliance_distance_m": safe_d, "avg_time_min": 6 if occupational else 30,
           "note": "EIRP should be time/duty averaged; screening only, not a full study"}
    if d_m:
        s = factor * eirp_w * 1000 / (4 * math.pi * (100 * d_m) ** 2)
        out.update({"S_mW_cm2": s, "percent_of_limit": 100 * s / limit,
                    "compliant": s <= limit})
    return out


# ---------- aviation VHF 8.33 / 25 kHz channel naming (ICAO Annex 10 Vol V) ----------

_833_OFFSET = {0: (0.0, 25), 5: (0.0, 8.33), 10: (25 / 3, 8.33), 15: (50 / 3, 8.33)}


def atc_channel(name):
    """Map an ATC channel name (e.g. 118.010) to its carrier frequency and spacing."""
    khz_total = round(float(name) * 1000)
    mhz_part, khz = divmod(khz_total, 1000)
    block, sub = divmod(khz, 25)
    if sub not in _833_OFFSET:
        raise ValueError(f"{name} is not a valid 25/8.33 kHz channel name "
                         "(last digits must end in .x00/.x05/.x10/.x15 per 25 kHz block)")
    offset, spacing = _833_OFFSET[sub]
    f_khz = mhz_part * 1000 + block * 25 + offset
    f_mhz = f_khz / 1000
    if not 118.0 <= f_mhz < 137.0:
        raise ValueError("ATC VHF band is 118.000-136.990 MHz")
    return {"channel_name": name, "frequency_MHz": round(f_mhz, 6), "spacing_kHz": spacing}


def atc_name(f_mhz, spacing_khz=8.33):
    """Inverse: frequency to channel name."""
    base = math.floor(f_mhz * 1000 / 25 + 1e-9) * 25
    off = f_mhz * 1000 - base
    if spacing_khz == 25:
        if abs(off) > 0.01:
            raise ValueError("not on a 25 kHz raster")
        return {"channel_name": f"{base / 1000:.3f}", "spacing_kHz": 25}
    idx = round(off / (25 / 3))
    if idx > 2 or abs(off - idx * 25 / 3) > 0.01:
        raise ValueError("not on an 8.33 kHz raster")
    return {"channel_name": f"{(base + 5 * (idx + 1)) / 1000:.3f}", "spacing_kHz": 8.33}
