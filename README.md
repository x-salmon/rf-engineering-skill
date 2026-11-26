# rf-engineering: a Claude skill

[![tests](https://github.com/x-salmon/rf-engineering-skill/actions/workflows/test.yml/badge.svg)](https://github.com/x-salmon/rf-engineering-skill/actions/workflows/test.yml)

A Claude Code / Claude Agent skill that makes Claude run real RF math instead of estimating it.
It has about 70 calculators covering link budgets, detection range, terrain, ITU-R rain and gas, digital comms, satellite, radar,
phase noise, mixers, filters, matching and antennas. It also includes a Touchstone sweep analyzer, plots, a
VISA instrument driver, and reference sheets for bands, formulas and install/acceptance standards.
The core runs on the Python 3.10+ standard library. `requirements-optional.txt` adds plots, ITU data maps,
elliptic filters and instrument control.

## Install
```bash
git clone https://github.com/x-salmon/rf-engineering-skill ~/.claude/skills/rf-engineering
pip install -r ~/.claude/skills/rf-engineering/requirements-optional.txt   # optional
# or as a CLI anywhere: pip install "rf-engineering-skill[full] @ git+https://github.com/x-salmon/rf-engineering-skill"
```
Claude loads it automatically when a question involves RF. It also works without Claude:
```bash
python scripts/rfcalc.py link --f 125MHz --d 100km --ptx 40 --gtx 2 --sens -107 --bw 25kHz --nf 8
python scripts/rfcalc.py profile 6GHz --fetch 40.015 -105.27 39.95 -105.10 --htx 30m --hrx 30m
python scripts/rfcalc.py --snap E12 filter 5 50MHz --kind chebyshev --ripple 0.1
python scripts/rfplot.py smith antenna.s1p --out smith.png
```

## What's inside
| Area | Commands |
|---|---|
| Link budget / detection | eirp, sens, fademargin (Rayleigh), pathloss (two-ray over real ground), clearance (obstacle vs F1), budget (margin + max range + horizon), detect-radar (Albersheim/Swerling vs RCS), detect-rf (passive emitter range) |
| Units | convert, dbsum, wavelength, eseries, global `--snap E12/E24/E96` |
| Links / propagation | fspl, link, fresnel, horizon, tworay, hata (Okumura-Hata + COST-231), field, doppler |
| Terrain / ITU-R | profile (SRTM fetch + Deygout), knife (P.526), rain (P.530/P.838/P.837), gas (P.676) |
| Receivers | noise, nftemp, cascade (Friis NF + IP3 + SFDR), imd, jitter, recipmix, mixer (image + spur plan) |
| Digital comms | ber (PSK/QAM/FSK/OOK, required Eb/N0, occupied BW), shannon |
| Satellite / radar | look, satlink, tsys, orbit, polloss, radar |
| Lines / matching | vswr, uncertainty, cable (LMR, RG, Heliax, semi-rigid), skin, coax, microstrip, zin, qwt, lmatch, pimatch, tmatch, stub (single/double) |
| Filters | filter (Butterworth/Chebyshev/Bessel LP/HP/BP), bessel (Darlington synthesis), elliptic, filterorder |
| Antennas / safety | antenna, array, isolation, helix, patch, mpe (FCC 1.1310 + OET-65) |
| Aviation | atc (ICAO 8.33/25 kHz channel naming) |
| Files / bench / plots | touchstone.py, instrument.py (read-only by default), rfplot.py (Smith, sweep, filter, path, array) |

## Link budgets and detection range

`scripts/rflink.py` adds link-budget and detection-range commands. Formulas, textbook check values and sources
are in [references/link-budget.md](references/link-budget.md).

Does a 900 MHz mobile link close with 99 % Rayleigh reliability?
```console
$ python scripts/rfcalc.py budget --f 900MHz --d 5km --ptx 30 --gtx 6 --grx 3 --ltx 2 --lrx 2 --bw 200kHz --nf 7 --snr 9 --reliability 99 --model tworay --ht 30m --hr 1.5m
eirp_dBm: 34
path_loss_model: tworay
path_loss_db: 115.0608
misc_loss_db: 0
received_dBm: -80.0608
noise_floor_dBm: -113.9649
snr_db: 33.9041
sensitivity_source: kTB + NF + SNR
sensitivity_dBm: -104.9649
required_fade_margin_db: 19.9782
link_margin_db: 24.9041
excess_margin_db: 4.9259
closes: True
max_range_km: 6.6455
radio_horizon_km: 27.6243
```

Does a ridge clear 60 % of the first Fresnel zone? (heights on one datum, e.g. ASL)
```console
$ python scripts/rfcalc.py clearance 6GHz 20km 8km --htx 140m --hrx 120m --hobs 110m
los_height_m: 132
earth_bulge_m: 5.6506
fresnel_f1_m: 15.4866
clearance_m: 16.3494
clearance_pct_f1: 105.5714
required_m: 9.2919
meets_requirement: True
raise_both_ends_by_m: 0
fresnel_v: -1.493
knife_edge_loss_db: 0
k_factor: 1.3333
```

Radar detection range for a small drone across an RCS band:
```console
$ python scripts/rfcalc.py detect-radar --pt 10 --g 30 --f 10GHz --rcs 0.01 0.1 --bw 1MHz --nf 5 --losses 6 --pulses 64 --hradar 5m --htarget 100m
required_snr_db: 13.1145
detection_model: Albersheim (Swerling 0)
pd: 0.9
pfa: 1u
coherent_pulses: 64
noncoherent_pulses: 1
ranges:
  rcs_m2=0.01, rcs_dBsm=-20, free_space_range_km=1.2944, detection_range_km=1.2944, horizon_limited=False
  rcs_m2=0.1, rcs_dBsm=-10, free_space_range_km=2.3018, detection_range_km=2.3018, horizon_limited=False
radar_horizon_km: 50.4349
warnings:
  free-space estimate: ground clutter, multipath and terrain masking usually shorten it for low-flying targets
```

Other commands: `eirp 37 --gtx 3 --ltx 1.5`, `sens 25kHz --nf 8 --snr 10`, `fademargin --reliability 99.9`,
`pathloss 900MHz 3km 30m 1.5m --ground sea --pol h`, and
`detect-rf --eirp 20 --f 2.44GHz --bw 10MHz --nf 6 --g 10 --hsensor 10m --htarget 100m`.
Detection ranges are clutter-free upper bounds. Clutter, multipath, terrain and target aspect usually shorten them.

See **[docs/examples.md](docs/examples.md)** for 28 worked problems with real output. They are regenerated by
`tools/gen_examples.py`, so the outputs always match the code.

## Validation
107 tests run in CI on Linux and Windows, with Python 3.10 and 3.13, both with and without the optional extras.
They check against published values: kT = -174 dBm/Hz, FSPL, the Matthaei Chebyshev and Bessel tables,
P.526 knife-edge (6 dB at grazing), P.838 coefficients, Hata, BPSK 9.6 dB at 1e-5, the Shannon limit, ISS orbit,
patch dimensions (Balanis), LMR datasheet points, Rayleigh margins (20 dB at 99 %, 30 dB at 99.9 %), the
Brewster-angle null, earth bulge d1 d2 / (12.74 k), Albersheim (13.1 dB at Pd 0.9 / Pfa 1e-6) and Swerling 1 (21.1 dB). Matching networks are checked by building the network
and confirming it presents the source impedance. Stub solutions check their own answers.

## Evals
`evals/evals.json` holds 7 prompts in the skill-creator format, each with expectations for grading Claude's
answer. Each also carries a reference `command` and numeric `checks`, which `tests/test_evals.py` runs in CI
so the expected answers can't drift from the code.

## Caveats
- Only the cables in `CABLE_CHECKED` are pinned to datasheet points. The others are approximate fits, and the
  output says which kind you got.
- Checklist values are typical; the governing spec wins. MPE output is a screening estimate only.
- Two-ray is flat-earth. Detection ranges ignore clutter, multipath and terrain masking; treat them as upper bounds.
- Elliptic gives order and notches but no LC element synthesis. ITU-R P.1546 is not included.
- `profile --fetch` sends coordinates to opentopodata.org. Use `--csv` for sites you can't share.
- Keep private site data in `references/site-local.md`, which git ignores.

MIT licensed.
