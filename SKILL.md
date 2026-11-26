---
name: rf-engineering
description: RF and radio engineering calculator with references. Use for any RF math or radio-system question - dBm/W/uV conversions, link budgets (EIRP, sensitivity, Rayleigh fade margin, max range), path loss (free-space, Hata, two-ray over real ground), Fresnel clearance at an obstacle, radar and passive-RF detection range for small aircraft/drones (Albersheim, Swerling), terrain path profiles with knife-edge/Deygout diffraction, ITU-R rain fade (P.530/P.838) and gas absorption (P.676), Fresnel zones and radio horizon, BER/Eb/N0/Shannon capacity, satellite look angles/G/T/C/N0/orbit Doppler, radar range equation, polarization loss, phase noise to jitter, reciprocal mixing, mixer spur/image planning, Bessel/elliptic filters, Pi/T/stub matching, E-series parts, antenna arrays/isolation/helix/patch, plots (Smith, path profile), noise floor and sensitivity, Friis noise/IP3 cascades, IMD products, VSWR/return loss/mismatch, coax cable loss, microstrip/coax impedance, L-matching, LC filter design, antenna gain/aperture, field strength, Doppler, FCC RF exposure (MPE), aviation VHF 8.33/25 kHz channel names, Touchstone .s1p/.s2p sweep analysis, spectrum-analyzer/sig-gen control over VISA, and install/test checklists (grounding, connector torque, sweep acceptance, FAT/SAT).
---

# RF engineering

Run the math, don't estimate it. Every number in an answer should come from a script, with the command
shown so the user can rerun it. Python 3.10+ standard library only. Scripts live in `scripts/` next to this file.

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

### Propagation (rfpath)
| Task | Command |
|---|---|
| Knife-edge diffraction (P.526) | `knife 1GHz 5km 5km 10m` (h = edge height above LOS) |
| Terrain profile + Deygout | `profile 6GHz --fetch LAT1 LON1 LAT2 LON2 --htx 30m --hrx 30m --save p.csv`, or `--csv p.csv` |
| Rain fade (P.530/P.838/P.837) | `rain 23GHz 15km --p 0.01 --lat 40 --lon -105`, or `--r001 42 --k .. --alpha ..` |
| Gas absorption (P.676) | `gas 60GHz 1km` |

`--fetch` sends coordinates to opentopodata.org. **Ask before fetching private site coordinates.**
`rain --lat/--lon` and `gas` need `pip install itur`.

### Comms, satellite, radar (rfcomms)
| Task | Command |
|---|---|
| BER / required Eb/N0 / bandwidth | `ber 64qam --target 1e-6 --rb 10M --rolloff 0.2` (bpsk qpsk dbpsk bfsk ncfsk ook Npsk Nqam) |
| Shannon | `shannon 20MHz --snr 15` / `shannon 20MHz --rate 100M` |
| Satellite look angles | `look 39.74 -104.99 --sat-lon -101` (GEO default; `--sat-lat --sat-alt` otherwise) |
| Satellite link | `satlink --eirp 52 --f 12GHz --range 38000km --gt 18 --losses 1 --rb 20M` |
| System temperature | `tsys 50 75 --feed-loss 0.3` |
| Orbit / Doppler | `orbit 550km --f 12GHz --min-el 25` |
| Polarization loss | `polloss 0 40 --tilt 0` (axial ratios in dB; `--opposite` for opposite sense) |
| Radar | `radar --pt 1M --g 33 --f 2.8GHz --rcs 1 --bw 1MHz --nf 4 --prf 1k --pulse 1us --pulses 10` |
| Phase noise to jitter | `jitter 100MHz 1k:-120 10k:-140 1M:-155 --from 12k --to 1M` |
| Reciprocal mixing | `recipmix -30 -125 25kHz --sens -110 --snr 10` |
| Mixer plan | `mixer 88MHz 108MHz 10.7MHz --side low --order 5` |

### Design (rfdesign)
| Task | Command |
|---|---|
| Bessel prototype | `bessel 4` (or `filter 5 50MHz --kind bessel`) |
| Elliptic order + notches | `elliptic 10MHz 13MHz --ripple 0.5 --atten 60` (scipy) |
| Pi / T match | `pimatch 12.5 50 145MHz --q 5` / `tmatch 50 10 100MHz --q 4` |
| Stub match | `stub 30+40j` / `stub 25-30j --double 0.125 --open` |
| Standard values | `eseries 3.3k --series E12`, or `--snap E24` before any command |
| Array | `array 8 0.5 --steer 30` |
| Antenna isolation | `isolation 150MHz 4m --mode vertical` |
| Helix / patch | `helix 1.2GHz 10` / `patch 2.45GHz --er 4.4 --h 1.6mm` |

### Link budget and detection (rflink)
| Task | Command |
|---|---|
| EIRP / ERP | `eirp 37 --gtx 3 --ltx 1.5` |
| Sensitivity | `sens 25kHz --nf 8 --snr 10` |
| Rayleigh fade margin | `fademargin --reliability 99.9` / `fademargin --margin 15` |
| Free space vs two-ray over ground | `pathloss 900MHz 3km 30m 1.5m --ground average --pol v` (sea fresh-water wet average dry pec) |
| Obstacle Fresnel clearance | `clearance 6GHz 20km 8km --htx 140m --hrx 120m --hobs 110m` (heights on one datum, e.g. ASL) |
| Link budget + max range | `budget --f 900MHz --d 5km --ptx 30 --gtx 6 --grx 3 --bw 200kHz --nf 7 --snr 9 --reliability 99 --model tworay --ht 30m --hr 1.5m` |
| Radar detection range vs RCS | `detect-radar --pt 10 --g 30 --f 10GHz --rcs 0.01 0.1 --bw 1MHz --nf 5 --losses 6 --pulses 64 --hradar 5m --htarget 100m` |
| Passive RF detection range | `detect-rf --eirp 20 --f 2.44GHz --bw 10MHz --nf 6 --g 10 --hsensor 10m --htarget 100m` |

`budget` takes `--sens` directly, or computes it from `--bw --nf --snr`. Required margin comes from `--fade`
or `--reliability` (Rayleigh). Two-ray range is scanned: `max_range_km` is continuous coverage up to the first null, and `last_lobe_km` is the farthest lobe that closes again (intermittent, so never quote it as coverage).
`detect-radar` uses Albersheim (`--target steady`, `--noncoh N`) or exact Swerling 1 (`--target swerling1`)
for the required SNR, and `--pulses` for coherent gain.

## Plots: `scripts/rfplot.py` (matplotlib)
`smith f.s1p`, `sweep f.s2p`, `filter 5 --kind chebyshev`, `profile p.csv --f 6GHz --htx 30 --hrx 30`,
`array 8 0.5 --steer 20`, each with `--out file.png`. Show the PNG to the user with the Read tool.

## Sweep files: `scripts/touchstone.py`
`touchstone.py file.s1p --rl 14 --at 118MHz 137MHz --csv out.csv` reports best match, the band that meets
the RL threshold, IL / -3 dB passband / group delay for .s2p, and values at chosen frequencies.

## Instruments: `scripts/instrument.py`
`list`, `idn`, `query`, `peak`, `trace --csv`, and `write --allow-write`. Read-only unless you pass
`--allow-write`. **Ask the user before any write that keys a transmitter or sig-gen output.**

## References (load on demand)
- `references/formulas.md`: every equation used, for showing working
- `references/link-budget.md`: rflink formulas, textbook check values and sources (ITU-R, Rappaport, Skolnik, Richards)
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
5. Optional extras (scipy, itur, matplotlib, pyvisa) are listed in `requirements-optional.txt`. If one is
   missing, say so and give the install command.
6. `docs/examples.md` has 28 worked problems with real output; use them as answer templates.
7. Detection ranges are free-space upper bounds. Give a band across several RCS or EIRP values, and say
   that clutter, multipath, terrain masking and target aspect usually cut them. Use only generic, public
   engineering: no specific operator's or vendor's system parameters.
8. Use scikit-rf/scipy only for work the scripts don't cover, and check the current API through context7 first.
