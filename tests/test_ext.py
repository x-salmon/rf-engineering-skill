"""Tests for propagation, comms, satellite, radar, design and antenna modules."""
import importlib.util
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import rfcalc  # noqa: E402
import rfcomms as cm  # noqa: E402
import rfcore  # noqa: E402
import rfdesign as ds  # noqa: E402
import rfpath as pa  # noqa: E402

HAS_ITUR = importlib.util.find_spec("itur") is not None
HAS_SCIPY = importlib.util.find_spec("scipy") is not None
HAS_MPL = importlib.util.find_spec("matplotlib") is not None


def _write_csv(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as fh:
        fh.write("distance_m,elevation_m\n")
        fh.writelines(f"{d},{e}\n" for d, e in rows)
    return path


class Diffraction(unittest.TestCase):
    def test_grazing_knife_edge_is_6db(self):
        self.assertAlmostEqual(pa.knife_edge_loss(0), 6.03, places=2)

    def test_no_loss_below_minus_078(self):
        self.assertEqual(pa.knife_edge_loss(-1), 0.0)

    def test_clear_flat_path_meets_60pct_f1_with_no_diffraction(self):
        path = _write_csv([(i * 100, 0) for i in range(101)])
        r = pa.analyze_profile(pa.load_profile_csv(path), 6e9, 60, 60)
        os.unlink(path)
        self.assertTrue(r["meets_60pct_F1"])
        self.assertEqual(r["diffraction_loss_db"], 0.0)

    def test_hill_blocks_path_and_single_edge_matches_knife_edge(self):
        rows = [(i * 100, 0) for i in range(101)]
        rows[50] = (5000, 40)
        path = _write_csv(rows)
        r = pa.analyze_profile(pa.load_profile_csv(path), 1e9, 10, 10, k=1e9)
        os.unlink(path)
        self.assertFalse(r["line_of_sight"])
        expect = pa.knife_edge(1e9, 5000, 5000, 30)["loss_db"]
        self.assertAlmostEqual(r["diffraction_loss_db"], expect, places=6)

    def test_great_circle_endpoints(self):
        pts = pa.great_circle_points(51.5, -0.12, 48.85, 2.35, 5)
        self.assertAlmostEqual(pts[-1][2] / 1e3, 343.5, delta=1.5)  # London-Paris


class Rain(unittest.TestCase):
    def test_p530_scaling_returns_a001_at_point_zero_one_pct(self):
        r = pa.rain_link(8, 20, 0.01, r001=42, k=0.00454, alpha=1.3270)
        self.assertAlmostEqual(r["A_p_db"] / r["A001_db"], 1.0, delta=0.01)

    def test_rain_fade_grows_for_rarer_events(self):
        a = pa.rain_link(18, 10, 0.1, r001=42, k=0.07078, alpha=1.0818)["A_p_db"]
        b = pa.rain_link(18, 10, 0.001, r001=42, k=0.07078, alpha=1.0818)["A_p_db"]
        self.assertGreater(b, a)

    @unittest.skipUnless(HAS_ITUR, "itur not installed")
    def test_p838_coefficients_from_itur(self):
        r = pa.rain_link(20, 5, 0.01, r001=30, pol="h")
        self.assertAlmostEqual(r["k"], 0.09164, places=4)

    @unittest.skipUnless(HAS_ITUR, "itur not installed")
    def test_oxygen_line_60ghz_about_15db_per_km(self):
        self.assertAlmostEqual(pa.gas_link(60, 1)["dB_per_km"], 15, delta=1.5)


class Comms(unittest.TestCase):
    def test_bpsk_needs_9_6db_for_1e_5(self):
        self.assertAlmostEqual(cm.required_ebn0("bpsk", 1e-5), 9.59, places=2)

    def test_shannon_limit(self):
        self.assertAlmostEqual(cm.shannon(1)["shannon_limit_EbN0_dB"], -1.59, places=2)

    def test_qpsk_bandwidth_with_rolloff(self):
        r = cm.modem("qpsk", rb=2e6, rolloff=0.25)
        self.assertAlmostEqual(r["occupied_bw_hz"], 1.25e6)

    def test_16qam_worse_than_qpsk(self):
        self.assertGreater(cm.ber("16qam", 10), cm.ber("qpsk", 10))


class Satellite(unittest.TestCase):
    def test_geo_overhead_on_equator(self):
        r = cm.look_angles(0, 0, 0, 0, 0)
        self.assertAlmostEqual(r["elevation_deg"], 90, places=3)
        self.assertAlmostEqual(r["slant_range_km"], 35786 + 6378.137 - 6378.137, delta=1)

    def test_iss_orbit(self):
        r = cm.orbit(420e3)
        self.assertAlmostEqual(r["period_min"], 92.8, delta=0.3)
        self.assertAlmostEqual(r["velocity_m_s"], 7660, delta=15)

    def test_cn0_identity(self):
        r = cm.sat_link(50, 12e9, 38000e3, gt_dbk=20)
        fspl = r["fspl_db"]
        self.assertAlmostEqual(r["C_N0_dBHz"], 50 - fspl + 20 + 228.6, places=1)

    def test_tsys_with_feed_loss(self):
        self.assertAlmostEqual(cm.system_temp(50, 100, 0.0), 150)


class Polarization(unittest.TestCase):
    def test_circular_into_linear_is_3db(self):
        self.assertAlmostEqual(cm.polarization_loss(0, 60)["polarization_loss_db"], 3.01, delta=0.01)

    def test_linear_at_45_deg_is_3db(self):
        self.assertAlmostEqual(cm.polarization_loss(60, 60, 45)["polarization_loss_db"], 3.01, 2)

    def test_matched_circular_is_lossless(self):
        self.assertAlmostEqual(cm.polarization_loss(0, 0)["polarization_loss_db"], 0, 6)


class Radar(unittest.TestCase):
    def test_snr_at_max_range_equals_threshold(self):
        r = cm.radar(1e6, 35, 3e9, 1, 1e6, 3, 13)
        s = cm.radar(1e6, 35, 3e9, 1, 1e6, 3, 13, range_m=r["max_range_km"] * 1e3)
        self.assertAlmostEqual(s["snr_at_range_db"], 13, places=6)

    def test_ambiguity(self):
        r = cm.radar(1e3, 30, 10e9, 1, 1e6, 3, prf_hz=1e3, pulse_s=1e-6)
        self.assertAlmostEqual(r["max_unambiguous_range_km"], 149.9, places=1)
        self.assertAlmostEqual(r["range_resolution_m"], 149.9, places=1)


class PhaseNoise(unittest.TestCase):
    def test_flat_phase_noise_integrates_exactly(self):
        r = cm.jitter(100e6, [(1e3, -100), (1e6, -100)])
        phi = math.sqrt(2 * 1e-10 * (1e6 - 1e3))
        self.assertAlmostEqual(r["rms_phase_rad"], phi, places=9)

    def test_reciprocal_mixing(self):
        r = cm.reciprocal_mixing(-30, -120, 10e3)
        self.assertAlmostEqual(r["reciprocal_mixing_noise_dBm"], -110)


class Mixer(unittest.TestCase):
    def test_low_side_image_and_half_if_spur(self):
        r = cm.mixer_plan(118e6, 137e6, 21.4e6, "low", 4)
        self.assertEqual(r["image_range_hz"], [118e6 - 42.8e6, 137e6 - 42.8e6])
        self.assertTrue(any(p["m_LO"] == 2 and p["n_RF"] == 2 and p["in_band"]
                            for p in r["products"]))


class Filters(unittest.TestCase):
    def test_bessel_matches_matthaei_delay_table(self):
        for a, b in zip(ds.bessel_g(3, "delay"), [1.2550, 0.5528, 0.1922]):
            self.assertAlmostEqual(a, b, places=4)

    def test_bessel_3db_normalized(self):
        g = ds.bessel_g(3)
        self.assertAlmostEqual(abs(ds.ladder_s21(g, 1.0)) ** 2, 0.5, places=6)

    def test_ladder_reproduces_butterworth_3db(self):
        g, _ = rfcore.prototype(5)
        self.assertAlmostEqual(20 * math.log10(abs(ds.ladder_s21(g, 1.0))), -3.0103, 3)

    def test_chebyshev_ladder_ripple(self):
        g, _ = rfcore.prototype(5, "chebyshev", 0.5)
        self.assertAlmostEqual(20 * math.log10(abs(ds.ladder_s21(g, 1.0))), -0.5, 3)

    @unittest.skipUnless(HAS_SCIPY, "scipy not installed")
    def test_elliptic_order(self):
        self.assertEqual(ds.elliptic(1e6, 1.5e6, 0.5, 60)["order"], 6)


def _zin(elements, zl, w):
    """Walk a ladder from load to source. elements: [('series'|'shunt', 'L'|'C', value)]."""
    z = zl
    for kind, part, v in reversed(elements):
        x = 1j * w * v if part == "L" else 1 / (1j * w * v)
        z = z + x if kind == "series" else 1 / (1 / z + 1 / x)
    return z


class Matching(unittest.TestCase):
    W = 2 * math.pi * 100e6

    def test_pi_match_presents_source_resistance(self):
        r = ds.pi_match(50, 1000, 100e6, 10)
        z = _zin([("shunt", "C", r["C1_F"]), ("series", "L", r["L_H"]),
                  ("shunt", "C", r["C2_F"])], 1000, self.W)
        self.assertAlmostEqual(z.real, 50, places=6)
        self.assertAlmostEqual(z.imag, 0, places=6)

    def test_t_match_presents_source_resistance(self):
        r = ds.t_match(50, 10, 100e6, 5)
        z = _zin([("series", "L", r["L1_H"]), ("shunt", "C", r["C_F"]),
                  ("series", "L", r["L2_H"])], 10, self.W)
        self.assertAlmostEqual(z.real, 50, places=6)

    def test_lmatch_presents_source_resistance(self):
        r = rfcore.l_match(50, 12.5, 100e6)["lowpass"]
        z = _zin([("shunt", "C", r["shunt_C_F"]), ("series", "L", r["series_L_H"])], 12.5,
                 self.W)
        self.assertAlmostEqual(z.real, 50, places=6)

    def test_single_and_double_stub_solutions_verify(self):
        for sol in ds.single_stub(100 + 50j)["solutions"]:
            self.assertLess(sol["verify_residual"], 1e-9)
        for sol in ds.double_stub(25 - 30j, spacing_wl=0.125)["solutions"]:
            self.assertLess(sol["verify_residual"], 1e-9)

    def test_eseries(self):
        self.assertEqual(ds.nearest(4600, "E24")["nearest"], 4700)
        self.assertAlmostEqual(ds.nearest(9.6e-12, "E12")["nearest"], 10e-12)


class Antennas(unittest.TestCase):
    def test_broadside_array_beamwidth(self):
        r = ds.array_factor(8, 0.5)
        self.assertAlmostEqual(r["hpbw_deg"], math.degrees(0.886 / 4), delta=0.2)

    def test_grating_lobe_warning(self):
        self.assertIn("warning", ds.array_factor(8, 0.9, steer_deg=30))

    def test_patch_2_45ghz_fr4(self):
        r = ds.patch(2.45e9, 4.4, 1.6e-3)
        self.assertAlmostEqual(r["width_m"] * 1e3, 37.26, delta=0.1)
        self.assertAlmostEqual(r["length_m"] * 1e3, 28.8, delta=0.3)

    def test_horizontal_isolation(self):
        r = ds.isolation(300e6, 10, "horizontal")
        lam = 299_792_458 / 300e6
        self.assertAlmostEqual(r["isolation_db"], 22 + 20 * math.log10(10 / lam) - 4.3, places=6)


class Cables(unittest.TestCase):
    def test_checked_cables_hit_datasheet_points(self):
        for name, points in rfcore.CABLE_CHECKED.items():
            for f_mhz, db100 in points:
                with self.subTest(cable=name, f=f_mhz):
                    got = rfcore.cable_loss(name, f_mhz, 1)["dB_per_100ft"]
                    self.assertLess(abs(got / db100 - 1), 0.05)

    def test_frequency_limit(self):
        with self.assertRaises(ValueError):
            rfcore.cable_loss("rg-58", 10000, 1)


class Cli(unittest.TestCase):
    def test_new_commands_run(self):
        cmds = [["knife", "1GHz", "5km", "5km", "10m"], ["ber", "16qam", "--target", "1e-6",
                                                         "--rb", "10M"],
                ["shannon", "20MHz", "--snr", "15"], ["look", "40", "-75", "--sat-lon", "-100"],
                ["orbit", "550km", "--f", "12GHz"], ["polloss", "0", "60"],
                ["radar", "--pt", "1M", "--g", "35", "--f", "3GHz", "--rcs", "1", "--bw", "1MHz",
                 "--nf", "3", "--prf", "1k", "--pulse", "1us"],
                ["jitter", "100MHz", "1k:-80", "1M:-140"], ["mixer", "88MHz", "108MHz",
                                                            "10.7MHz"],
                ["bessel", "4"], ["pimatch", "50", "500", "30MHz", "--q", "8"],
                ["stub", "30+40j"], ["eseries", "3.3k"], ["array", "16", "0.5", "--steer", "30"],
                ["isolation", "150MHz", "3m", "--mode", "vertical"], ["helix", "1.2GHz", "10"],
                ["patch", "5.8GHz", "--er", "3.48", "--h", "0.76mm"],
                ["--snap", "E24", "filter", "5", "50MHz", "--kind", "bessel"]]
        if HAS_SCIPY:
            cmds.append(["elliptic", "10MHz", "13MHz"])
        for argv in cmds:
            with self.subTest(argv=argv):
                self.assertEqual(rfcalc.main(["--json", *argv]), 0)

    @unittest.skipUnless(HAS_MPL, "matplotlib not installed")
    def test_plots_write_files(self):
        import rfplot
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "f.png")
            self.assertEqual(rfplot.main(["filter", "5", "--kind", "chebyshev", "--out", out]), 0)
            self.assertTrue(os.path.getsize(out) > 1000)
            out2 = os.path.join(d, "a.png")
            self.assertEqual(rfplot.main(["array", "8", "0.5", "--out", out2]), 0)


if __name__ == "__main__":
    unittest.main()
