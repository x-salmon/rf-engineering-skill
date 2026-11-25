"""Terrain path profiles, knife-edge diffraction (ITU-R P.526) and ITU-R rain/gas attenuation.

Terrain heights come from a CSV (distance_m,elev_m) or, with --fetch, from the public
OpenTopoData API (SRTM 30 m). Fetching sends the two endpoint coordinates and the sampled
points to that service. ITU rain/gas models use ITU-Rpy (`pip install itur`) for the
P.837/P.838/P.676 data tables; P.530 rain scaling is implemented here directly.
"""
import csv
import json
import math
import urllib.parse
import urllib.request

from rfargs import dist, freq
from rfcore import C0

EARTH_R_M = 6_371_000.0
TOPO_URL = "https://api.opentopodata.org/v1/{dataset}?locations={locs}"
TOPO_MAX_POINTS = 100
HTTP_TIMEOUT_S = 30


# ---------- diffraction ----------

def knife_edge_loss(v):
    """ITU-R P.526 eq. 31: J(v) = 6.9 + 20 log10(sqrt((v-0.1)^2 + 1) + v - 0.1), v > -0.78."""
    if v <= -0.78:
        return 0.0
    return 6.9 + 20 * math.log10(math.sqrt((v - 0.1) ** 2 + 1) + v - 0.1)


def fresnel_v(h_m, d1_m, d2_m, lam_m):
    return h_m * math.sqrt(2 * (d1_m + d2_m) / (lam_m * d1_m * d2_m))


def knife_edge(f_hz, d1_m, d2_m, h_m):
    lam = C0 / f_hz
    v = fresnel_v(h_m, d1_m, d2_m, lam)
    return {"v": v, "loss_db": knife_edge_loss(v),
            "fresnel_radius_m": math.sqrt(lam * d1_m * d2_m / (d1_m + d2_m))}


# ---------- terrain ----------

def great_circle_points(lat1, lon1, lat2, lon2, n):
    """n points (inclusive) along the great circle; returns [(lat, lon, dist_m)]."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2
                                + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2))
    out = []
    for i in range(n):
        f = i / (n - 1)
        if d == 0:
            out.append((lat1, lon1, 0.0))
            continue
        a = math.sin((1 - f) * d) / math.sin(d)
        b = math.sin(f * d) / math.sin(d)
        x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
        y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
        z = a * math.sin(p1) + b * math.sin(p2)
        out.append((math.degrees(math.atan2(z, math.hypot(x, y))),
                    math.degrees(math.atan2(y, x)), f * d * EARTH_R_M))
    return out


def fetch_profile(lat1, lon1, lat2, lon2, n=TOPO_MAX_POINTS, dataset="srtm30m"):
    n = max(2, min(n, TOPO_MAX_POINTS))
    pts = great_circle_points(lat1, lon1, lat2, lon2, n)
    locs = "|".join(f"{la:.6f},{lo:.6f}" for la, lo, _ in pts)
    url = TOPO_URL.format(dataset=urllib.parse.quote(dataset), locs=urllib.parse.quote(locs, safe=",|."))
    req = urllib.request.Request(url, headers={"User-Agent": "rf-engineering-skill"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:  # noqa: S310 (fixed https host)
        data = json.load(resp)
    if data.get("status") != "OK":
        raise ValueError(f"elevation service error: {data.get('error', data.get('status'))}")
    elev = [r.get("elevation") for r in data["results"]]
    if len(elev) != len(pts):
        raise ValueError(f"elevation service returned {len(elev)} of {len(pts)} points")
    if any(e is None for e in elev):
        raise ValueError("elevation service returned gaps (sea or outside dataset)")
    return [(d, float(e)) for (_, _, d), e in zip(pts, elev)]


def load_profile_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or row[0].strip().lower().startswith(("d", "#")):
                continue
            rows.append((float(row[0]), float(row[1])))
    if len(rows) < 3:
        raise ValueError("profile needs at least 3 points (distance_m, elevation_m)")
    return sorted(rows)


def analyze_profile(profile, f_hz, h_tx_m, h_rx_m, k=4 / 3, clutter_m=0.0):
    """LOS clearance, first-Fresnel clearance and Deygout diffraction over a terrain profile."""
    lam = C0 / f_hz
    total = profile[-1][0] - profile[0][0]
    d0 = profile[0][0]
    re = k * EARTH_R_M
    y_tx = profile[0][1] + h_tx_m
    y_rx = profile[-1][1] + h_rx_m
    pts = []
    for d, e in profile[1:-1]:
        x = d - d0
        bulge = x * (total - x) / (2 * re)
        ground = e + bulge + clutter_m
        los = y_tx + (y_rx - y_tx) * x / total
        r1 = math.sqrt(lam * x * (total - x) / total)
        pts.append({"d_m": x, "terrain_m": e, "effective_m": ground, "los_m": los,
                    "clearance_m": los - ground, "f1_m": r1,
                    "clearance_f1": (los - ground) / r1})
    worst = min(pts, key=lambda p: p["clearance_f1"])
    diff = deygout([(p["d_m"], p["effective_m"]) for p in pts], 0.0, y_tx, total, y_rx, lam)
    fspl = 20 * math.log10(4 * math.pi * total / lam)
    return {
        "path_km": total / 1e3, "k_factor": k, "lambda_m": lam,
        "worst_point_km": worst["d_m"] / 1e3, "worst_clearance_m": worst["clearance_m"],
        "worst_clearance_pct_F1": 100 * worst["clearance_f1"],
        "line_of_sight": worst["clearance_m"] > 0,
        "meets_60pct_F1": worst["clearance_f1"] >= 0.6,
        "diffraction_loss_db": diff, "fspl_db": fspl,
        "total_path_loss_db": fspl + diff, "points": pts,
    }


def deygout(pts, xa, ya, xb, yb, lam, depth=0, max_depth=2):
    """Deygout multiple knife-edge: main edge, then up to one subsidiary edge each side."""
    best, best_v = None, -0.78
    for x, h in pts:
        if not xa < x < xb:
            continue
        los = ya + (yb - ya) * (x - xa) / (xb - xa)
        v = fresnel_v(h - los, x - xa, xb - x, lam)
        if v > best_v:
            best, best_v = (x, h), v
    if best is None:
        return 0.0
    loss = knife_edge_loss(best_v)
    if depth < max_depth:
        loss += deygout(pts, xa, ya, best[0], best[1], lam, depth + 1, max_depth)
        loss += deygout(pts, best[0], best[1], xb, yb, lam, depth + 1, max_depth)
    return loss


# ---------- ITU-R rain and gas ----------

def _itur():
    try:
        import itur  # noqa: F401
        from itur.models import itu676, itu837, itu838
    except ImportError as exc:
        raise ValueError("this needs ITU-Rpy: pip install itur "
                         "(or pass --k/--alpha and --r001 yourself)") from exc
    return itu676, itu837, itu838


def rain_link(f_ghz, d_km, p_pct=0.01, r001=None, lat=None, lon=None, pol="v",
              k=None, alpha=None):
    """ITU-R P.530-17 sec. 2.4.1 rain attenuation exceeded p % of an average year."""
    if k is None or alpha is None:
        _, _, i838 = _itur()
        tau = 90 if pol == "v" else 0
        k, alpha = (float(x) for x in i838.rain_specific_attenuation_coefficients(f_ghz, 0, tau))
    if r001 is None:
        if lat is None or lon is None:
            raise ValueError("give --r001 (mm/h) or --lat/--lon for the P.837 map")
        _, i837, _ = _itur()
        r001 = float(i837.rainfall_rate(lat, lon, 0.01).value)
    gamma = k * r001 ** alpha
    r = 1 / (0.477 * d_km ** 0.633 * r001 ** (0.073 * alpha) * f_ghz ** 0.123
             - 10.579 * (1 - math.exp(-0.024 * d_km)))
    r = min(r, 2.5)
    a001 = gamma * d_km * r
    c0 = 0.12 + 0.4 * math.log10((f_ghz / 10) ** 0.8) if f_ghz >= 10 else 0.12
    c1 = 0.07 ** c0 * 0.12 ** (1 - c0)
    c2 = 0.855 * c0 + 0.546 * (1 - c0)
    c3 = 0.139 * c0 + 0.043 * (1 - c0)
    ap = a001 * c1 * p_pct ** -(c2 + c3 * math.log10(p_pct))
    out = {"R001_mm_h": r001, "k": k, "alpha": alpha, "gamma_dB_km": gamma,
           "distance_factor_r": r, "A001_db": a001, "p_pct": p_pct, "A_p_db": ap,
           "availability_pct": 100 - p_pct}
    if not 0.001 <= p_pct <= 1:
        out["warning"] = "P.530 scaling is defined for 0.001 % <= p <= 1 %"
    return out


def gas_link(f_ghz, d_km, rho_g_m3=7.5, p_hpa=1013.25, t_k=288.15):
    """ITU-R P.676 Annex 1 line-by-line specific attenuation over a horizontal path."""
    i676, _, _ = _itur()
    a = i676.gaseous_attenuation_terrestrial_path(d_km, f_ghz, 0, rho_g_m3, p_hpa, t_k, "exact")
    total = float(getattr(a, "value", a))
    return {"gas_loss_db": total, "dB_per_km": total / d_km, "rho_g_m3": rho_g_m3,
            "pressure_hPa": p_hpa, "temp_K": t_k}


# ---------- CLI ----------

def register(sp):
    a = sp.add_parser("knife", help="single knife-edge diffraction loss (P.526)")
    a.add_argument("f", type=freq)
    a.add_argument("d1", type=dist)
    a.add_argument("d2", type=dist)
    a.add_argument("h", type=dist, help="edge height above the LOS line (negative = below)")
    a.set_defaults(func=lambda x: knife_edge(x.f, x.d1, x.d2, x.h))

    a = sp.add_parser("profile", help="terrain path: LOS, Fresnel clearance, Deygout loss")
    a.add_argument("f", type=freq)
    a.add_argument("--csv", help="profile CSV: distance_m,elevation_m")
    a.add_argument("--fetch", nargs=4, type=float, metavar=("LAT1", "LON1", "LAT2", "LON2"),
                   help="download SRTM heights from opentopodata.org")
    a.add_argument("--htx", type=dist, required=True, help="TX antenna height above ground")
    a.add_argument("--hrx", type=dist, required=True)
    a.add_argument("--k", type=float, default=4 / 3)
    a.add_argument("--clutter", type=dist, default=0.0, help="trees/buildings added to terrain")
    a.add_argument("--points", action="store_true", help="include every sample in output")
    a.add_argument("--save", help="write the fetched profile to CSV")
    a.set_defaults(func=_profile_cmd)

    a = sp.add_parser("rain", help="rain fade for a terrestrial link (P.530 / P.838 / P.837)")
    a.add_argument("f", type=freq)
    a.add_argument("d", type=dist)
    a.add_argument("--p", type=float, default=0.01, help="time %% exceeded (0.01 = 99.99 %%)")
    a.add_argument("--r001", type=float, help="rain rate exceeded 0.01 %% (mm/h)")
    a.add_argument("--lat", type=float)
    a.add_argument("--lon", type=float)
    a.add_argument("--pol", choices=["h", "v"], default="v")
    a.add_argument("--k", type=float)
    a.add_argument("--alpha", type=float)
    a.set_defaults(func=lambda x: rain_link(x.f / 1e9, x.d / 1e3, x.p, x.r001, x.lat, x.lon,
                                            x.pol, x.k, x.alpha))

    a = sp.add_parser("gas", help="oxygen + water vapour loss on a path (P.676)")
    a.add_argument("f", type=freq)
    a.add_argument("d", type=dist)
    a.add_argument("--rho", type=float, default=7.5, help="water vapour g/m^3")
    a.add_argument("--p", type=float, default=1013.25, help="pressure hPa")
    a.add_argument("--t", type=float, default=288.15, help="temperature K")
    a.set_defaults(func=lambda x: gas_link(x.f / 1e9, x.d / 1e3, x.rho, x.p, x.t))


def _profile_cmd(x):
    if x.csv:
        prof = load_profile_csv(x.csv)
    elif x.fetch:
        prof = fetch_profile(*x.fetch)
        if x.save:
            with open(x.save, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerows([("distance_m", "elevation_m"), *prof])
    else:
        raise ValueError("give --csv FILE or --fetch LAT1 LON1 LAT2 LON2")
    out = analyze_profile(prof, x.f, x.htx, x.hrx, x.k, x.clutter)
    if not x.points:
        out.pop("points")
    return out
