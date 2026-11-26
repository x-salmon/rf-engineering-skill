"""Link-budget module checks against textbook values (sources in references/link-budget.md)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import rfcalc  # noqa: E402
import rfcomms as cm  # noqa: E402
import rflink as lk  # noqa: E402
import rfprop as p  # noqa: E402
from rfcore import C0, K_BOLTZMANN, T0  # noqa: E402


class FreeSpace(unittest.TestCase):
    def test_fspl_2_4ghz_100m_is_80_05db(self):
        # 20 log d_km + 20 log f_MHz + 32.44 = -20 + 67.60 + 32.44
        self.assertAlmostEqual(lk.path_loss("fspl", 100, 2.4e9), 80.05, places=2)

    def test_fspl_range_inverts_the_loss(self):
        r = lk.max_range(lk.path_loss("fspl", 12_345, 900e6), 900e6)
        self.assertAlmostEqual(r["max_range_m"], 12_345, places=6)


class TwoRay(unittest.TestCase):
    def test_far_field_rappaport_form_50m_1_5m_5km(self):
        # PL = 40 log d - 20 log(ht hr) = 147.96 - 37.50
        r = lk.two_ray_ground(5000, 900e6, 50, 1.5)
        self.assertAlmostEqual(r["two_ray_far_db"], 110.46, places=2)

    def test_exact_pec_converges_to_40db_per_decade_far_out(self):
        r = lk.two_ray_ground(200e3, 900e6, 30, 2, "pec")
        self.assertAlmostEqual(r["path_loss_db"], r["two_ray_far_db"], delta=0.05)

    def test_pec_matches_existing_two_ray(self):
        new = lk.two_ray_ground(50e3, 900e6, 30, 2, "pec")["path_loss_db"]
        old = p.two_ray(50e3, 900e6, 30, 2)["two_ray_exact_db"]
        self.assertAlmostEqual(new, old, places=3)

    def test_crossover_is_4pi_ht_hr_over_lambda(self):
        r = lk.two_ray_ground(1000, 900e6, 30, 1.5)
        self.assertAlmostEqual(r["crossover_m"], 4 * math.pi * 45 / (C0 / 900e6), places=6)

    def test_short_range_lobing_stays_within_6db_of_free_space(self):
        # constructive peak can at most double the field (+6 dB) before the crossover
        for d in range(50, 1500, 7):
            r = lk.two_ray_ground(d, 900e6, 30, 1.5)
            self.assertGreaterEqual(r["path_loss_db"], r["fspl_db"] - 6.03)


class GroundReflection(unittest.TestCase):
    def test_grazing_incidence_gives_minus_one_for_both_polarizations(self):
        for pol in ("h", "v"):
            g = lk.ground_gamma(1e-9, 1e9, "average", pol)
            self.assertAlmostEqual(g.real, -1, places=6)

    def test_vertical_pol_vanishes_at_brewster_angle(self):
        # lossless ground: sin(psi_B) = 1 / sqrt(er + 1) (Rappaport 4.27)
        lk.GROUNDS["_lossless"] = (15.0, 0.0)
        try:
            psi = math.asin(1 / math.sqrt(16))
            self.assertAlmostEqual(abs(lk.ground_gamma(psi, 1e9, "_lossless", "v")), 0,
                                   places=9)
        finally:
            del lk.GROUNDS["_lossless"]

    def test_horizontal_pol_at_normal_incidence(self):
        # psi = 90 deg: |G| = (sqrt(er) - 1) / (sqrt(er) + 1) for a lossless dielectric
        lk.GROUNDS["_lossless"] = (9.0, 0.0)
        try:
            g = lk.ground_gamma(math.pi / 2, 1e9, "_lossless", "h")
            self.assertAlmostEqual(abs(g), 0.5, places=9)
        finally:
            del lk.GROUNDS["_lossless"]

    def test_unknown_ground_rejected(self):
        with self.assertRaises(ValueError):
            lk.ground_gamma(0.1, 1e9, "lava")


class Clearance(unittest.TestCase):
    def test_earth_bulge_textbook_form_d1_d2_over_12_74k(self):
        r = lk.clearance(2.4e9, 10e3, 5e3, 30, 30, 0)
        self.assertAlmostEqual(r["earth_bulge_m"], 25 / (12.74 * 4 / 3), places=2)
        self.assertAlmostEqual(r["fresnel_f1_m"], 17.68, places=1)

    def test_grazing_obstacle_is_zero_clearance_and_6db(self):
        r = lk.clearance(1e9, 10e3, 5e3, 50, 50, 50, k=1e12)
        self.assertAlmostEqual(r["clearance_m"], 0, places=6)
        self.assertAlmostEqual(r["knife_edge_loss_db"], 6.03, places=2)
        self.assertFalse(r["meets_requirement"])

    def test_raise_by_brings_clearance_to_60pct(self):
        r = lk.clearance(6e9, 20e3, 8e3, 40, 40, 35)
        lifted = lk.clearance(6e9, 20e3, 8e3, 40 + r["raise_both_ends_by_m"],
                              40 + r["raise_both_ends_by_m"], 35)
        self.assertAlmostEqual(lifted["clearance_pct_f1"], 60, places=6)

    def test_obstacle_outside_path_rejected(self):
        with self.assertRaises(ValueError):
            lk.clearance(1e9, 10e3, 12e3, 10, 10, 0)


class Budget(unittest.TestCase):
    def test_eirp_1w_plus_3dbi_minus_1db(self):
        r = lk.eirp(30, 3, 1)
        self.assertAlmostEqual(r["eirp_dBm"], 32)
        self.assertAlmostEqual(r["erp_dBm"], 29.85)

    def test_sensitivity_25khz_nf8_snr10_is_minus_112dbm(self):
        self.assertAlmostEqual(lk.sensitivity(25e3, 8, 10)["sensitivity_dBm"], -112.0,
                               places=1)

    def test_rayleigh_margins_20_and_30_db(self):
        self.assertAlmostEqual(lk.rayleigh_fade_margin(0.99), 20.0, delta=0.03)
        self.assertAlmostEqual(lk.rayleigh_fade_margin(0.999), 30.0, delta=0.01)
        self.assertAlmostEqual(lk.rayleigh_reliability(20.0), 0.99005, places=5)

    def test_budget_arithmetic_and_zero_margin_range(self):
        r = lk.budget(1e9, 10e3, 30, g_tx=10, g_rx=10, l_tx=2, l_rx=2, sens_dbm=-90,
                      fade_db=10)
        pl = p.fspl(10e3, 1e9)["fspl_db"]
        self.assertAlmostEqual(r["received_dBm"], 30 - 2 + 10 - pl + 10 - 2)
        self.assertAlmostEqual(r["excess_margin_db"], r["received_dBm"] + 90 - 10)
        at_max = lk.budget(1e9, r["max_range_km"] * 1e3, 30, 10, 10, 2, 2, sens_dbm=-90,
                           fade_db=10)
        self.assertAlmostEqual(at_max["excess_margin_db"], 0, places=6)

    def test_two_ray_range_is_continuous_and_lobe_reported_separately(self):
        r = lk.max_range(117.98, 2.44e9, "tworay", 10, 100)
        self.assertLess(r["max_range_m"], r["last_lobe_m"])
        just_past = r["max_range_m"] * (lk.SCAN_MAX_M / lk.SCAN_MIN_M) ** (1 / (lk.SCAN_POINTS - 1))
        self.assertGreater(lk.path_loss("tworay", just_past, 2.44e9, 10, 100), 117.98)

    def test_scan_limit_is_flagged(self):
        self.assertIn("warning", lk.max_range(400, 1e9, "tworay", 30, 30))

    def test_fade_margin_rejects_both_inputs(self):
        with self.assertRaises(ValueError):
            lk.fade_margin(0.99, 10)

    def test_beyond_horizon_is_flagged(self):
        r = lk.budget(150e6, 80e3, 40, sens_dbm=-110, ht_m=10, hr_m=10)
        self.assertIn("warning", r)

    def test_missing_sensitivity_inputs_raise(self):
        with self.assertRaises(ValueError):
            lk.budget(1e9, 1e3, 30, bw_hz=1e6)


class Detection(unittest.TestCase):
    def test_albersheim_pd09_pfa1e6_single_pulse_about_13_1db(self):
        # Richards, Fundamentals of Radar Signal Processing: Albersheim ~13.1 dB, exact 13.2
        self.assertAlmostEqual(lk.albersheim_snr(0.9, 1e-6), 13.1, delta=0.1)
        self.assertAlmostEqual(lk.albersheim_snr(0.5, 1e-6), 11.2, delta=0.1)

    def test_albersheim_integration_lowers_per_pulse_snr(self):
        self.assertLess(lk.albersheim_snr(0.9, 1e-6, 10), lk.albersheim_snr(0.9, 1e-6, 1) - 7)

    def test_swerling1_single_pulse_exact_about_21_1db(self):
        self.assertAlmostEqual(lk.swerling1_snr(0.9, 1e-6), 21.14, places=2)

    def test_radar_range_from_the_equation_by_hand(self):
        pt, g, f, rcs, bw, nf = 1e3, 30, 10e9, 0.01, 1e6, 5
        r = lk.detect_radar(pt, g, f, [rcs], bw, nf)
        snr = 10 ** (lk.albersheim_snr(0.9, 1e-6) / 10)
        lam = C0 / f
        r4 = (pt * 1e6 * lam ** 2 * rcs) / ((4 * math.pi) ** 3 * K_BOLTZMANN * T0 * bw
                                             * 10 ** (nf / 10) * snr)
        self.assertAlmostEqual(r["ranges"][0]["free_space_range_km"], r4 ** 0.25 / 1e3,
                               places=9)

    def test_range_scales_as_fourth_root_of_rcs(self):
        r = lk.detect_radar(1e3, 30, 10e9, [0.01, 0.16], 1e6, 5)["ranges"]
        self.assertAlmostEqual(r[1]["free_space_range_km"] / r[0]["free_space_range_km"], 2,
                               places=9)

    def test_horizon_caps_low_target(self):
        r = lk.detect_radar(1e6, 40, 3e9, [1], 1e6, 3, h_radar_m=5, h_target_m=20)
        self.assertTrue(r["ranges"][0]["horizon_limited"])
        self.assertAlmostEqual(r["ranges"][0]["detection_range_km"], r["radar_horizon_km"])

    def test_snr_at_reported_range_equals_requirement(self):
        r = lk.detect_radar(1e3, 30, 10e9, [0.1], 1e6, 5, losses_db=4, n_coh=16)
        rng = r["ranges"][0]["free_space_range_km"] * 1e3
        s = cm.radar(1e3, 30, 10e9, 0.1, 1e6, 5, losses_db=4, n_pulses=16, range_m=rng)
        self.assertAlmostEqual(s["snr_at_range_db"], r["required_snr_db"], places=6)

    def test_passive_rf_free_space_range_closes_at_sensitivity(self):
        r = lk.detect_rf(20, 2.44e9, 10e6, 6, 10, g_sensor=10)
        pl = lk.path_loss("fspl", r["free_space_range_km"] * 1e3, 2.44e9)
        self.assertAlmostEqual(20 + 10 - pl, r["sensitivity_dBm"], places=6)

    def test_bad_rcs_and_pulse_counts_rejected(self):
        with self.assertRaises(ValueError):
            lk.detect_radar(1e3, 30, 10e9, [0], 1e6, 5)
        with self.assertRaises(ValueError):
            lk.detect_radar(1e3, 30, 10e9, [1], 1e6, 5, n_coh=0)

    def test_bad_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            lk.required_snr(1e-6, 0.9)


class Cli(unittest.TestCase):
    def test_every_link_command_runs(self):
        cmds = [["eirp", "37", "--gtx", "3", "--ltx", "1.5"],
                ["sens", "25kHz", "--nf", "8", "--snr", "10"],
                ["fademargin", "--reliability", "99.9"], ["fademargin", "--margin", "15"],
                ["pathloss", "900MHz", "3km", "30m", "1.5m", "--ground", "sea", "--pol", "h"],
                ["clearance", "6GHz", "20km", "8km", "--htx", "140m", "--hrx", "120m",
                 "--hobs", "110m"],
                ["budget", "--f", "900MHz", "--d", "5km", "--ptx", "30", "--bw", "200kHz",
                 "--nf", "7", "--snr", "9", "--reliability", "99", "--model", "tworay",
                 "--ht", "30m", "--hr", "1.5m"],
                ["detect-radar", "--pt", "10", "--g", "30", "--f", "10GHz", "--rcs", "0.01",
                 "0.1", "--bw", "1MHz", "--nf", "5", "--hradar", "5m", "--htarget", "100m"],
                ["detect-rf", "--eirp", "20", "--f", "2.44GHz", "--bw", "10MHz", "--nf", "6",
                 "--hsensor", "10m", "--htarget", "100m"]]
        for argv in cmds:
            with self.subTest(argv=argv):
                self.assertEqual(rfcalc.main(["--json", *argv]), 0)


if __name__ == "__main__":
    unittest.main()
