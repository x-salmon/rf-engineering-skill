# Link budget and detection range (what `scripts/rflink.py` implements)

Load this when you need to show working for `eirp`, `sens`, `fademargin`, `pathloss`, `clearance`,
`budget`, `detect-radar` or `detect-rf`. Each section lists the formula, the test that pins it to a
textbook value (`tests/test_link.py`), and the source.

## Power and sensitivity
- EIRP(dBm) = Ptx - Lfeeder + Gtx(dBi); ERP = EIRP - 2.15 dB
- Noise floor = 10 log10(k T0 B) + 30 + NF, with kT0 = -173.98 dBm/Hz at T0 = 290 K
- Sensitivity = floor + required SNR (or Eb/N0 + 10 log(Rb / B))
- Received = EIRP - PL - Lmisc + Grx - Lrx; link margin = received - sensitivity;
  excess margin = link margin - required fade margin
- Check: 25 kHz, NF 8 dB, SNR 10 dB gives -112.0 dBm
- Source: Friis, "Noise figures of radio receivers", Proc. IRE 32 (1944); IEEE Std 145 (antenna terms)

## Fade margin (Rayleigh)
- Received power in Rayleigh fading is exponential: P(p < p_mean / F) = 1 - exp(-1/F)
- Margin for reliability R: F = -1 / ln(R); FM(dB) = -10 log10(-ln R)
- Check: 90 % = 9.8 dB, 99 % = 20.0 dB, 99.9 % = 30.0 dB, the usual 10 dB per decade of outage
- This is worst-case (no line-of-sight path). A line-of-sight link fades less, so use `--fade` with a
  measured or Rician figure when you have one. Microwave availability (P.530 multipath and rain) is a
  separate calculation (`rain`).
- Source: Rappaport, *Wireless Communications: Principles and Practice*, 2nd ed., ch. 5 (Rayleigh
  distribution); Sklar, *Digital Communications*, 2nd ed., ch. 15

## Free-space path loss
- FSPL = 20 log10(4 pi d / lambda) = 20 log d_km + 20 log f_MHz + 32.44
- Check: 1 km at 1 GHz = 92.45 dB; 100 m at 2.4 GHz = 80.05 dB
- Valid in the far field only (d >> lambda, and d > 2 D^2 / lambda for an aperture D)
- Source: ITU-R P.525 (calculation of free-space attenuation); Friis, Proc. IRE 34 (1946)

## Two-ray ground reflection
- Direct path r1 = sqrt(d^2 + (ht - hr)^2); reflected path r2 = sqrt(d^2 + (ht + hr)^2)
- PL = FSPL(r1) - 20 log10 | 1 + Gamma (r1 / r2) exp(-j k (r2 - r1)) |
- Grazing angle psi = atan((ht + hr) / d). Complex permittivity ec = er - j 60 sigma lambda
- Gamma_h = (sin psi - sqrt(ec - cos^2 psi)) / (sin psi + sqrt(ec - cos^2 psi))
- Gamma_v = (ec sin psi - sqrt(ec - cos^2 psi)) / (ec sin psi + sqrt(ec - cos^2 psi))
- Far field (Gamma -> -1, d beyond crossover 4 pi ht hr / lambda): PL = 40 log d - 20 log(ht hr)
- Checks: Gamma -> -1 at grazing for both polarizations; Gamma_v = 0 at the Brewster angle
  sin psi_B = 1 / sqrt(er + 1) on lossless ground; ht 50 m, hr 1.5 m, 5 km gives 110.46 dB far-field
- Before the crossover the field oscillates about free space within +6 / -inf dB. Max range is found
  by scanning. `max_range_km` / `two_ray_range_km` is continuous coverage up to the first null that breaks
  the link; `last_lobe_km` is the farthest lobe that closes again, which is intermittent coverage only. The
  grid steps 0.36 %, so a null narrower than that can be missed.
- Flat earth only, with no curvature divergence factor, so treat it as an approximation past about 10 % of the
  radio horizon.
- Source: Rappaport, 2nd ed., sec. 4.5-4.6 (reflection, Brewster angle, two-ray model); Parsons,
  *The Mobile Radio Propagation Channel*, 2nd ed., ch. 2

### Ground constants (`--ground`), typical VHF/UHF values after ITU-R P.527
| Preset | er | sigma (S/m) |
|---|---|---|
| sea | 70 | 5 |
| fresh-water | 80 | 0.003 |
| wet | 30 | 0.01 |
| average (medium dry) | 15 | 0.001 |
| dry | 3 | 0.0001 |
| pec | ideal reflector, Gamma = -1 | |

These change with frequency, moisture and temperature. They are good enough for a model, but they aren't measurements.

## Fresnel zone clearance at an obstacle
- Line-of-sight height at the obstacle: h_los = h_tx + (h_rx - h_tx) d1 / d (all heights on one datum)
- Earth bulge: b = d1 d2 / (2 k Re); in km and metres, b = d1 d2 / (12.74 k)
- F1 radius: r1 = sqrt(lambda d1 d2 / d)
- Clearance c = h_los - (h_obs + b); the usual criterion is c >= 0.6 r1 at k = 4/3 (stricter planning
  also checks k = 2/3)
- Diffraction parameter v = -sqrt(2) c / r1; loss J(v) = 6.9 + 20 log(sqrt((v-0.1)^2+1) + v - 0.1)
  for v > -0.78, otherwise 0
- Checks: 10 km at 2.4 GHz, midpoint F1 = 17.68 m and bulge 1.47 m; grazing obstacle (c = 0) = 6.0 dB
- Source: ITU-R P.526 (Fresnel ellipsoid, single knife edge); ITU-R P.530 (clearance criteria,
  k-factor); Freeman, *Radio System Design for Telecommunications*, 3rd ed. (earth bulge)

## Radio horizon
- d = sqrt(2 k Re h) per end; k = 4/3 gives d_km ~= 4.12 sqrt(h_m). Sum both ends for the max LOS.
- Source: ITU-R P.834 / P.453 (effective earth radius)

## Radar detection range
- Radar equation: R^4 = Pt G^2 lambda^2 sigma N_coh / ((4 pi)^3 k T0 B F L SNR_req)
- Albersheim (steady target, N noncoherent pulses, SNR per pulse):
  A = ln(0.62 / Pfa), B = ln(Pd / (1 - Pd)),
  SNR = -5 log10 N + (6.2 + 4.54 / sqrt(N + 0.44)) log10(A + 0.12 A B + 1.7 B).
  Fitted for Pfa 1e-7..1e-3, Pd 0.1..0.9, N 1..8096, with error under about 0.2 dB
- Swerling 1, single pulse (exact): Pd = Pfa^(1 / (1 + SNR)), so SNR = ln Pfa / ln Pd - 1
- Checks: Pd 0.9 / Pfa 1e-6, N = 1 gives 13.1 dB (Albersheim) vs 13.2 dB exact; Pd 0.5 gives 11.2 dB;
  Swerling 1 needs 21.1 dB; range scales with sigma^(1/4)
- Coherent integration (`--pulses`) divides the required SNR by N. Noncoherent integration (`--noncoh`)
  goes through Albersheim.
- Source: Skolnik, *Introduction to Radar Systems*, 3rd ed., ch. 2; Richards, *Fundamentals of Radar
  Signal Processing*, 2nd ed., ch. 6; Albersheim, "A closed-form approximation to Robertson's detection
  characteristics", Proc. IEEE 69(7), 1981

### Small-aircraft (drone) targets
- Published RCS measurements of small multirotors mostly fall between about -20 and -10 dBsm (0.01-0.1 m^2).
  They swing by 10 dB or more with aspect angle, frequency and polarization, so pass several values to
  `--rcs` and present a range band rather than a single number.
- For low, slow targets, clutter, multipath (propagation factor F^4), terrain masking and the Doppler
  processing set the practical range more often than thermal noise does. The output is an upper bound.
- Source: Patel, Fioranelli and Anderson, "Review of radar classification and RCS characterisation
  techniques for small UAVs or drones", IET Radar, Sonar & Navigation 12(9), 2018

## Passive RF detection range
- Allowed loss = emitter EIRP + Gsensor - Lsensor - Lmisc - sensitivity(B, NF, SNR)
- Range = the largest d with PL(d) <= allowed loss, under free space and two-ray, capped by the radio horizon
- Match the sensor bandwidth to the emitter's occupied bandwidth. A wider bandwidth raises the noise
  floor by 10 log(B_sensor / B_signal).
- Frequency-hopping and bursty emitters also need dwell time and revisit rate, which this module
  does not model.
