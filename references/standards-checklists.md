# Install, test and acceptance checklists

Typical industry values. The contract, site spec or OEM manual always overrides them. Quote the
governing document when a value goes into a test report.

## Governing standards to know
| Topic | Standard |
|---|---|
| Site grounding, bonding, surge (LMR) | Motorola R56; TIA-607 (telecom bonding); NFPA 70 Art. 250/810/820 |
| FAA facilities | FAA-STD-019 (lightning/surge), FAA-STD-020 (transient protection), FAA Order 6950.19 |
| Military | MIL-STD-188-124 (grounding/bonding/shielding), MIL-STD-461 (EMI) |
| Towers | ANSI/TIA-222 (structural), TIA-1019 (construction safety) |
| RF exposure | FCC 47 CFR 1.1310, OET Bulletin 65; IEEE C95.1 |
| Coax connectors | IEC 61169 series; MIL-STD-348 (interfaces) |
| Lightning protection | NFPA 780, IEC 62305 |

## Connector torque (typical)
| Connector | Torque |
|---|---|
| SMA (brass) | 5 in-lb (0.56 N m); stainless 8 in-lb |
| 3.5 mm / 2.92 mm | 8 in-lb (0.9 N m) |
| TNC | 12-15 in-lb |
| BNC | bayonet; no torque spec |
| N-type | 12-15 in-lb (1.4-1.7 N m) |
| 7/16 DIN | 220 in-lb (25 N m) |
| 4.3-10 | 45 in-lb (5 N m) screw type |
Use a calibrated torque wrench and hold the body with a backing wrench. Never spin the body.

## Coax handling
- Minimum bend radius: about 10x OD for one-time install, 20x for repeated flexing (check datasheet)
- Weatherproof outdoor joints: self-amalgamating tape, then vinyl tape, wound upward to shed water
- Drip loop before entry; ground kit at tower top, base and building entry (R56)
- Install the surge protector at the entry panel, bonded to the master ground bar by the shortest path

## Sweep testing (cable and antenna)
1. Calibrate the analyzer (OSL) at the end of the test lead, over the band of interest
2. Return loss of the whole system: acceptance is often >= 15 dB (VSWR 1.43) for antenna systems
   and >= 20 dB (VSWR 1.22) for a cable with a load. Use the spec value.
3. Distance-to-fault (DTF): set cable VF and loss/ft; look for spikes at connectors, kinks and water
4. Cable loss test: short or open the far end; insertion loss = (one-way RL reading) / 2
5. Save traces as .s1p and run `touchstone.py` for numbers in the report
6. PIM (for multi-carrier sites): typical acceptance -153 dBc with 2 x 43 dBm tones

## Radio TX/RX acceptance (AM aviation VHF example)
| Test | Typical method |
|---|---|
| TX power | through-line wattmeter or attenuator + power meter; within +/-1 dB of spec |
| Frequency error | counter or analyzer; 8.33 kHz requires tighter tolerance (about 1 ppm, check ED-23C / DO-186) |
| Modulation depth | AM 85 % to 95 % at 1 kHz tone, no overmodulation |
| Spurious and harmonics | analyzer; compare to the radio's spec or the regulatory mask |
| RX sensitivity | sig gen at 30 % AM, 1 kHz; level for the specified SINAD (often about -101 to -107 dBm) |
| Squelch | open/close threshold and hysteresis |
| Audio | level into 600 ohm, frequency response 300-3400 Hz |
| VSWR alarm | fault the line; alarm must trip at the stated threshold |

## FAT / SAT checklist outline
1. Pre-test: build state, firmware versions, test equipment with calibration dates, drawings and cable list revision
2. Visual: labels match the cable list, connectors torqued, bend radius, grounding and bonding
3. Continuity / insulation on every cable before power-up; record port to port
4. Power-up sequence with currents logged
5. Functional RF tests (table above), interface tests (E&M, PTT, COR), switchover and redundancy
6. Alarm and monitoring checks: each alarm triggered and cleared
7. Record deviations with root cause, fix and retest; get sign-off from the witnesses

## Grounding quick values
- Target ground electrode resistance: 5 ohm or less for comms sites (R56); 10 ohm or less is common for
  FAA facilities (check STD-019/6950.19). Measure by fall-of-potential, 3-point method.
- Bond with #2 AWG solid tinned copper or larger for external rings; exothermic welds below grade
- Single-point ground window for equipment rooms; no ground loops between racks
