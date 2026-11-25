# Frequency reference

Public allocations and common service bands. Allocation details vary by country and change.
For anything licensed, check the national table (US: 47 CFR 2.106 / NTIA Redbook; ICAO Annex 10
for aviation). Site-specific channel plans belong in a separate private file (see the bottom).

## Aeronautical
| Service | Frequency | Notes |
|---|---|---|
| Marker beacons | 75 MHz | OM/MM/IM, AM-modulated tones 400/1300/3000 Hz |
| ILS localizer | 108.10-111.95 MHz | odd tenths (108.10, 108.15, 108.30, ...); paired with glideslope |
| VOR | 108.00-117.95 MHz | 50 kHz spacing; terminal VORs on even tenths below 112 |
| VHF COM (ATC voice) | 118.000-136.990 MHz | AM (A3E). 25 kHz worldwide, 8.33 kHz in Europe above FL195 and widely below. `rfcalc atc` converts channel names |
| Emergency (VHF guard) | 121.5 MHz | also the ELT homing signal |
| Air-to-air | 123.450 MHz | |
| ACARS / VDL Mode 2 | 131.550, 136.700-136.975 MHz | data link |
| Military UHF air | 225.000-399.975 MHz | AM, 25 kHz; 243.0 MHz is UHF guard |
| ILS glideslope | 328.6-335.4 MHz | paired with localizer channel |
| ELT 406 | 406.0-406.1 MHz | Cospas-Sarsat digital beacon |
| DME / TACAN | 960-1215 MHz | pulse pairs; TACAN = DME + bearing |
| SSR interrogation | 1030 MHz | Mode A/C/S, ground to air |
| SSR reply / ADS-B 1090ES | 1090 MHz | air to ground |
| UAT (US ADS-B) | 978 MHz | below 18,000 ft in the US |
| GNSS | L5 1176.45, L2 1227.60, L1 1575.42 MHz | GPS; Galileo E1 shares 1575.42 |
| Long-range radar (ARSR) | 1215-1400 MHz | L-band primary surveillance |
| Airport surveillance (ASR) | 2700-2900 MHz | S-band; NEXRAD weather radar also here |
| TDWR | 5600-5650 MHz | terminal Doppler weather radar |
| Radar altimeter | 4200-4400 MHz | protected; 5G C-band interference issue |
| HF aero (en route) | 2.85-22 MHz bands | USB voice, HF datalink |

### 8.33 kHz channel naming
Each 25 kHz block holds 3 channels at 8.33 kHz. The displayed name is not the carrier:

| Name | Carrier | Spacing |
|---|---|---|
| 118.000 | 118.0000 | 25 kHz |
| 118.005 | 118.0000 | 8.33 |
| 118.010 | 118.0083 | 8.33 |
| 118.015 | 118.0167 | 8.33 |
| 118.025 | 118.0250 | 25 kHz |
| 118.030 / .035 / .040 | 118.0250 / .0333 / .0417 | 8.33 |

Names ending in .x20, .x45, .x70, .x95 do not exist.

## Maritime and land mobile (US)
| Service | Frequency |
|---|---|
| Marine VHF | 156.000-162.025 MHz; Ch16 156.800 distress, Ch70 156.525 DSC |
| AIS | 161.975, 162.025 MHz |
| NOAA Weather Radio | 162.400-162.550 MHz |
| VHF high band LMR | 150-174 MHz |
| UHF LMR | 450-470 MHz |
| FRS/GMRS | 462.5625-462.725, 467.5625-467.725 MHz |
| Public safety 700/800 | 758-775 / 788-805 MHz, 806-824 / 851-869 MHz |
| MURS | 151.820-154.600 MHz (5 channels) |

## Unlicensed / ISM (US)
| Band | Frequency |
|---|---|
| ISM 13.56 / 27.12 MHz | RFID, induction |
| 433 MHz | 433.05-434.79 (Region 1 ISM; US Part 15 periodic) |
| 902-928 MHz | ISM, LoRa US915, RFID |
| 2.4 GHz | 2400-2483.5 MHz, Wi-Fi, BT, Zigbee |
| 5 GHz U-NII | 5150-5350, 5470-5725, 5725-5850 MHz |
| 6 GHz U-NII-5..8 | 5925-7125 MHz, Wi-Fi 6E/7 |
| 24 GHz ISM | 24.00-24.25 GHz |
| 60 GHz | 57-71 GHz |

## Amateur (US, abbreviated)
160 m 1.8-2.0, 80 m 3.5-4.0, 40 m 7.0-7.3, 20 m 14.0-14.35, 15 m 21.0-21.45, 10 m 28.0-29.7 MHz,
6 m 50-54, 2 m 144-148, 1.25 m 222-225, 70 cm 420-450, 33 cm 902-928, 23 cm 1240-1300 MHz.

## Radar band letters (IEEE 521)
HF 3-30 MHz, VHF 30-300 MHz, UHF 300-1000 MHz, L 1-2 GHz, S 2-4, C 4-8, X 8-12, Ku 12-18,
K 18-27, Ka 27-40, V 40-75, W 75-110 GHz.

## Your site plan (keep private)
Put site channel plans, radio part numbers and interface specs in `references/site-local.md`.
That file is in `.gitignore` so it never reaches the public repo.
