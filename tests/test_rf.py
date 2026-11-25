"""Checks against textbook / datasheet values. Run: python -m pytest tests  (or unittest)."""
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import rfcalc  # noqa: E402
import rfcore as c  # noqa: E402
import rfprop as p  # noqa: E402
import touchstone  # noqa: E402


class Units(unittest.TestCase):
    def test_zero_dbm_is_one_milliwatt_and_224mv_in_50_ohm(self):
        r = c.convert_power(0, "dbm")
        self.assertAlmostEqual(r["mW"], 1.0)
        self.assertAlmostEqual(r["Vrms"], 0.2236, places=4)
        self.assertAlmostEqual(r["dBuV"], 106.99, places=2)

    def test_two_equal_signals_sum_to_plus_3db(self):
        self.assertAlmostEqual(c.db_sum([-50, -50])["sum_dBm"], -46.99, places=2)

    def test_quantity_parser_keeps_milli_and_mega_distinct(self):
        self.assertEqual(rfcalc.freq("2.4GHz"), 2.4e9)
        self.assertEqual(rfcalc.freq("118.5MHz"), 118.5e6)
        self.assertAlmostEqual(rfcalc.qty("4.7pF", "F"), 4.7e-12)
        self.assertAlmostEqual(rfcalc.dist("3mi"), 4828.032)


class Noise(unittest.TestCase):
    def test_kt_at_290k_is_minus_174_dbm_per_hz(self):
        self.assertAlmostEqual(c.noise_floor(1)["kTB_dBm"], -173.98, places=2)

    def test_friis_cascade_lna_then_noisy_mixer(self):
        # F = 1.2589 + (10-1)/100 = 1.3489 -> 1.30 dB
        r = c.cascade([{"gain_db": 20, "nf_db": 1}, {"gain_db": 10, "nf_db": 10}])
        self.assertAlmostEqual(r["total_nf_db"], 1.2998, places=3)
        self.assertAlmostEqual(r["total_gain_db"], 30)

    def test_iip3_cascade_second_stage_dominates(self):
        r = c.cascade([{"gain_db": 20, "nf_db": 1, "oip3_dbm": 30},
                       {"gain_db": 0, "nf_db": 6, "oip3_dbm": 10}])
        # IIP3s: 10 dBm and 10 dBm (referred by 20 dB gain -> -10) => ~ -10.04 dBm
        self.assertAlmostEqual(r["iip3_dBm"], -10.04, places=2)

    def test_nf_temperature_round_trip(self):
        self.assertAlmostEqual(c.nf_to_temp(3.0103), 290, places=1)
        self.assertAlmostEqual(c.temp_to_nf(c.nf_to_temp(2.5)), 2.5)


class Mismatch(unittest.TestCase):
    def test_vswr_2(self):
        r = c.mismatch(vswr=2)
        self.assertAlmostEqual(r["gamma_mag"], 1 / 3)
        self.assertAlmostEqual(r["return_loss_db"], 9.542, places=3)
        self.assertAlmostEqual(r["mismatch_loss_db"], 0.512, places=3)

    def test_75_ohm_into_50_is_vswr_1_5(self):
        self.assertAlmostEqual(c.mismatch(zl=75)["vswr"], 1.5)


class Lines(unittest.TestCase):
    def test_lmr400_at_900mhz_matches_datasheet_3_9db(self):
        r = c.cable_loss("lmr-400", 900, 30.48)
        self.assertAlmostEqual(r["dB_per_100ft"], 3.9, delta=0.15)

    def test_rg58_air_dielectric_geometry(self):
        self.assertAlmostEqual(c.coax_z0(2.3, 1.0)["z0_ohm"], 49.97, places=1)

    def test_fr4_50_ohm_microstrip_is_about_1_9h(self):
        w = c.microstrip_width(50, 1.0, 4.4)["width"]
        self.assertAlmostEqual(w, 1.91, delta=0.05)

    def test_quarter_wave_inverts_impedance(self):
        r = c.line_input_impedance(100, 50, 90)
        self.assertAlmostEqual(r["zin_real"], 25)

    def test_copper_skin_depth_at_1ghz_is_2_06um(self):
        self.assertAlmostEqual(c.skin_depth(1e9)["skin_depth_um"], 2.06, places=2)


class Filters(unittest.TestCase):
    def test_butterworth_3rd_order_prototype(self):
        g, _ = c.prototype(3)
        for a, b in zip(g, [1, 2, 1]):
            self.assertAlmostEqual(a, b)

    def test_chebyshev_05db_3rd_order_matches_matthaei_table(self):
        g, gl = c.prototype(3, "chebyshev", 0.5)
        for a, b in zip(g, [1.5963, 1.0967, 1.5963]):
            self.assertAlmostEqual(a, b, places=3)
        self.assertEqual(gl, 1.0)

    def test_lmatch_50_to_200(self):
        r = c.l_match(50, 200, 100e6)
        self.assertAlmostEqual(r["Q"], math.sqrt(3))


class Propagation(unittest.TestCase):
    def test_fspl_1km_1ghz_is_92_45db(self):
        self.assertAlmostEqual(p.fspl(1000, 1e9)["fspl_db"], 92.45, places=2)

    def test_fresnel_radius_10km_link_at_midpoint_2_4ghz(self):
        self.assertAlmostEqual(p.fresnel(5000, 5000, 2.4e9)["fresnel_radius_m"], 17.68,
                               places=1)

    def test_radio_horizon_10m_is_about_13km(self):
        self.assertAlmostEqual(p.radio_horizon(10)["horizon_tx_km"], 13.03, places=1)

    def test_hata_urban_900mhz_reference_point(self):
        r = p.hata(900, 1, 30, 1.5)
        self.assertAlmostEqual(r["path_loss_db"], 126.4, delta=0.3)

    def test_mpe_general_public_limit_at_150mhz(self):
        self.assertAlmostEqual(p.mpe(100, 150)["limit_mW_cm2"], 0.2)


class Aviation(unittest.TestCase):
    def test_833_names(self):
        self.assertAlmostEqual(p.atc_channel("118.010")["frequency_MHz"], 118.008333, 5)
        self.assertEqual(p.atc_channel("118.025")["spacing_kHz"], 25)
        self.assertAlmostEqual(p.atc_channel("132.090")["frequency_MHz"], 132.091667, 5)

    def test_invalid_name_rejected(self):
        with self.assertRaises(ValueError):
            p.atc_channel("118.020")

    def test_inverse(self):
        self.assertEqual(p.atc_name(118.0166667)["channel_name"], "118.015")


class TouchstoneParse(unittest.TestCase):
    def test_s1p_db_format_finds_band(self):
        body = "# MHz S DB R 50\n100 -5 0\n110 -15 0\n120 -20 0\n130 -15 0\n140 -5 0\n"
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.s1p")
            with open(path, "w") as fh:
                fh.write(body)
            f, m, z0, n = touchstone.parse(path)
        self.assertEqual(n, 1)
        rl = [-touchstone.db(x[0][0]) for x in m]
        band = touchstone.bands_above(f, rl, 10)
        self.assertAlmostEqual(band[0][0], 105e6)
        self.assertAlmostEqual(band[0][1], 135e6)


class Cli(unittest.TestCase):
    def test_every_command_runs(self):
        cmds = [
            ["convert", "-30", "dbm"], ["fspl", "121.5MHz", "50km"],
            ["link", "--f", "125MHz", "--d", "100km", "--ptx", "40", "--gtx", "2",
             "--sens", "-107", "--bw", "25kHz", "--nf", "8"],
            ["cascade", "-1:1", "20:0.8:30", "-6:6:20", "--bw", "25kHz"],
            ["vswr", "--zl", "30-20j"], ["cable", "lmr-400", "1GHz", "30m"],
            ["filter", "5", "100MHz", "--kind", "chebyshev"],
            ["filter", "3", "118MHz", "--f2", "137MHz", "--resp", "bandpass"],
            ["hata", "450MHz", "5km", "40m", "1.5m"], ["mpe", "125MHz", "50", "--d", "3m"],
            ["atc", "121.500"], ["zin", "--zl", "100", "--len", "0.5m", "--f", "150MHz"],
            ["imd", "--f1", "120MHz", "--f2", "121MHz"], ["tworay", "1GHz", "2km", "30m", "2m"],
        ]
        for argv in cmds:
            with self.subTest(argv=argv):
                self.assertEqual(rfcalc.main(["--json", *argv]), 0)


if __name__ == "__main__":
    unittest.main()
