---
name: rf-engineering
description: RF and radio engineering calculator with references. Use for any RF math or radio-system question - dBm/W/uV conversions, link budgets, path loss (free-space, Hata, two-ray), Fresnel zones and radio horizon, noise floor and sensitivity, Friis noise/IP3 cascades, IMD products, VSWR/return loss/mismatch, coax cable loss, microstrip/coax impedance, L-matching, LC filter design, antenna gain/aperture, field strength, Doppler, FCC RF exposure (MPE), aviation VHF 8.33/25 kHz channel names, Touchstone .s1p/.s2p sweep analysis, spectrum-analyzer/sig-gen control over VISA, and install/test checklists (grounding, connector torque, sweep acceptance, FAT/SAT).
---

# RF engineering

Run the math, don't estimate it. Every number in an answer should come from a script, with the command
shown so the user can rerun it. Python 3.9+ standard library only. Scripts live in `scripts/` next to this file.

## Calculator: `scripts/rfcalc.py`

Quantities take suffixes: `2.4GHz 118.5MHz 25kHz 10km 300m 3mi 100ft 4.7pF 10nH`. Add `--json` before the
command for structured output. `rfcalc.py <cmd> -h` lists every option.

| Task | Command |
|---|---|
| Unit conversion | `convert -30 dbm` / `convert 1 uv` / `convert 5 w` (`--z0 75`) |
| Sum signal levels | `dbsum -50 -53 -60` |
| Wavelength, antenna cut | `wavelength 146MHz --vf 0.66` |
| Free-space loss | `fspl 121.5MHz 50km` |
| Link budget | `link --f 125MHz --d 100km --ptx 40 --gtx 2 --grx 0 --ltx 2 --lrx 2 --sens -107 --bw 25kHz --nf 8` |
| Noise floor / sensitivity | `noise 25kHz --nf 8 --snr 10` |
| NF <-> temperature | `nftemp --nf 1.5` / `nftemp --te 75` |
| RX chain cascade | `cascade -1:1 20:0.8:30 -6:6:20 --bw 25kHz` (stage = gain:NF[:OIP3]) |
| IMD level / products | `imd --pin -20 --iip3 10` / `imd --f1 120MHz --f2 121MHz --order 3` |
| VSWR / RL / gamma | `vswr --vswr 1.5` / `vswr --rl 14` / `vswr --zl 30-20j` |
| Mismatch uncertainty | `uncertainty 1.3 1.5` |
| Coax loss | `cable lmr-400 1GHz 30m` (lmr-195/240/400/600/900, rg-58, rg-8x, rg-213, or `--k1 --k2`) |
| Skin depth | `skin 100MHz` |
| Coax / microstrip Z0 | `coax 7.24 2.26 --er 1.38` / `microstrip --h 1.6 --er 4.4 --z0 50` |
| Line input impedance | `zin --zl 100 --len 0.5m --f 150MHz --vf 0.66` |
| Quarter-wave transformer | `qwt 50 200` |
| L-match | `lmatch 50 12.5 145MHz` |
| Reactance / resonance | `reactance 100MHz --L 100nH --C 10pF` |
| LC filter | `filter 5 30MHz --kind chebyshev --ripple 0.1` / `filter 3 118MHz --f2 137MHz --resp bandpass` |
| Filter order | `filterorder 100MHz 200MHz 40` |
| Fresnel / clearance | `fresnel 2.4GHz 3km 7km` |
| Radio horizon | `horizon 30m 10000ft` |
| Two-ray ground | `tworay 900MHz 2km 30m 1.5m` |
| Hata / COST-231 | `hata 450MHz 5km 40m 1.5m --env suburban` |
| Field strength | `field --eirp 50 --d 1km` / `field --prx -60 --f 125MHz --g 2` |
| Antenna | `antenna 10GHz --dia 1.2m` / `antenna 1GHz --gain 15` |
| Doppler | `doppler 1090MHz 250 --angle 30` |
| RF exposure | `mpe 125MHz 50 --d 2m` (EIRP in W; `--occupational`) |
| ATC channel | `atc 118.010` / `atc 132.0916667 --freq` |

## Sweep files: `scripts/touchstone.py`
`touchstone.py file.s1p --rl 14 --at 118MHz 137MHz --csv out.csv` reports best match, the band that meets
the RL threshold, IL / -3 dB passband / group delay for .s2p, and values at chosen frequencies.

## Instruments: `scripts/instrument.py`
`list`, `idn`, `query`, `peak`, `trace --csv`, and `write --allow-write`. Read-only unless you pass
`--allow-write`. **Ask the user before any write that keys a transmitter or sig-gen output.**

## References (load on demand)
- `references/formulas.md`: every equation used, for showing working
- `references/bands.md`: aviation, maritime, LMR, ISM, amateur allocations; 8.33 kHz naming
- `references/standards-checklists.md`: R56 / FAA-STD-019 / MIL-STD-188-124, torque, sweep acceptance, FAT/SAT
- `references/instruments.md`: SCPI tables, VISA strings, scikit-rf/scipy/GNU Radio starters
- `references/site-local.md` (optional, git-ignored): the user's private site channel plans and radios

## Rules
1. State the assumptions with every result: k-factor, Z0, temperature, model validity range. Pass on any
   `warning` that a script returns.
2. Report a link budget as a table: EIRP, path loss, received level, floor, SNR and margin. Mark any range
   beyond the radio horizon as unreachable.
3. Cable coefficients and checklist values are typical. Tell the user to confirm them against the datasheet
   or the governing spec before sign-off.
4. MPE output is a screening estimate, not a compliance study.
5. Use scikit-rf/scipy only for work the scripts don't cover, and check the current API through context7 first.
