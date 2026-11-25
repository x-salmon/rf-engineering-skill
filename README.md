# rf-engineering: a Claude skill

A Claude Code / Claude Agent skill that makes Claude run real RF math instead of estimating it.
It has 30+ calculators, a Touchstone sweep analyzer, a VISA instrument driver, and reference sheets for
bands, formulas and install/acceptance standards. Everything runs on the Python 3.9+ standard library.

## Install
```bash
git clone https://github.com/<you>/rf-engineering-skill ~/.claude/skills/rf-engineering
```
Claude loads it automatically when a question involves RF. It also works without Claude:
```bash
python scripts/rfcalc.py link --f 125MHz --d 100km --ptx 40 --gtx 2 --sens -107 --bw 25kHz --nf 8
python scripts/rfcalc.py cascade -1:1 20:0.8:30 -6:6:20 --bw 25kHz
python scripts/rfcalc.py atc 118.010
python scripts/touchstone.py antenna.s1p --rl 14
```

## What's inside
| Area | Commands |
|---|---|
| Units | convert, dbsum, wavelength |
| Links / propagation | fspl, link, fresnel, horizon, tworay, hata (Okumura-Hata + COST-231), field, doppler |
| Receivers | noise, nftemp, cascade (Friis NF + IP3 + SFDR), imd |
| Lines / matching | vswr, uncertainty, cable, skin, coax, microstrip, zin, qwt, lmatch, reactance |
| Filters | filter (Butterworth/Chebyshev LP/HP/BP ladders), filterorder |
| Antennas / safety | antenna, mpe (FCC 1.1310 + OET-65) |
| Aviation | atc (ICAO 8.33/25 kHz channel naming) |
| Files / bench | touchstone.py (.s1p/.s2p), instrument.py (pyvisa, read-only by default) |

## Validation
`python -m unittest discover tests` checks the code against textbook and datasheet values: kT = -174 dBm/Hz,
FSPL(1 km, 1 GHz) = 92.45 dB, the Matthaei Chebyshev tables, Hata reference values, LMR-400 loss, Cu skin depth,
and the 8.33 kHz channel names.

## Caveats
Cable coefficients and checklist values are typical. Always confirm against the datasheet or the governing
spec. MPE is a screening estimate only. Keep private site data in `references/site-local.md`, which git ignores.

MIT licensed.
