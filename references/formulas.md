# Formula sheet (what the scripts implement)

Load this when you need to show working or check a hand calculation.

## Units
- P(dBm) = 10 log10(P / 1 mW); dBW = dBm - 30
- V_rms = sqrt(P * Z0); 0 dBm into 50 ohm = 223.6 mV = 107 dBuV
- dBuV = dBm + 107 (50 ohm); dBuV = dBm + 108.75 (75 ohm)
- EIRP = ERP + 2.15 dB (dBi = dBd + 2.15)

## Noise
- kT = -173.98 dBm/Hz at T0 = 290 K
- Floor = -174 + 10 log10(B) + NF; sensitivity = floor + required SNR (or Eb/N0 + 10 log Rb)
- Te = T0 (F - 1); F = 10^(NF/10)
- Friis: F = F1 + (F2-1)/G1 + (F3-1)/(G1 G2) + ...
- Passive loss L at T0 has NF = L dB
- Cascade IIP3: 1/IIP3 = sum(G_before_i / IIP3_i), linear mW
- IM3 out = 3 Pin - 2 IIP3 (+ gain); SFDR = 2/3 (IIP3 - floor)

## Mismatch
- Gamma = (ZL - Z0)/(ZL + Z0); VSWR = (1+|G|)/(1-|G|)
- RL = -20 log|G|; mismatch loss = -10 log(1 - |G|^2)
- Mismatch uncertainty = 20 log(1 +/- |G1||G2|)

## Lines
- Coax Z0 = (59.96 / sqrt(er)) ln(D/d); VF = 1/sqrt(er)
- Zin = Z0 (ZL + j Z0 tan bl) / (Z0 + j ZL tan bl); quarter wave: Zin = Z0^2/ZL
- Quarter-wave transformer Zt = sqrt(Z1 Z2)
- Microstrip: Hammerstad-Jensen quasi-static (see rfcore.microstrip)
- Skin depth d = sqrt(rho / (pi f mu)); Cu at 1 GHz = 2.06 um
- Cable loss model: dB/100 ft = k1 sqrt(f_MHz) + k2 f_MHz

## Matching and filters
- L-match Q = sqrt(Rhi/Rlo - 1); Xseries = Q Rlo; Xshunt = Rhi / Q
- Butterworth g_k = 2 sin((2k-1) pi / 2n)
- Chebyshev: b = ln(coth(Lr/17.37)), g = sinh(b/2n), standard Matthaei recursion
- LP: C = g/(Z0 w), L = g Z0/w. HP: C = 1/(g Z0 w), L = Z0/(g w)
- BP: series L = g Z0/(w0 FBW), series C = FBW/(w0 g Z0); shunt C = g/(w0 FBW Z0), shunt L = FBW Z0/(w0 g)

## Propagation
- FSPL = 20 log10(4 pi d / lambda) = 20 log d_km + 20 log f_MHz + 32.44
- Fresnel r_n = sqrt(n lambda d1 d2 / d); clear 60 % of F1 plus earth bulge d1 d2 / (2 k Re)
- Radio horizon d = sqrt(2 k Re h); with k = 4/3, d_km ~= 4.12 sqrt(h_m)
- Two-ray far field: PL = 40 log d - 20 log(ht hr); crossover d = 4 pi ht hr / lambda
- Okumura-Hata 150-1500 MHz, COST-231 to 2000 MHz, d 1-20 km, hb 30-200 m, hm 1-10 m
- E (V/m) = sqrt(30 EIRP_W) / d; E(dBuV/m) = Prx(dBm) + 20 log f_MHz - G_dBi + 77.2
- Doppler fd = v f cos(theta) / c

## Antennas
- Ae = G lambda^2 / (4 pi); dish G = eta (pi D / lambda)^2; HPBW ~= 70 lambda / D deg
- Far field starts at 2 D^2 / lambda

## Exposure (FCC 47 CFR 1.1310, mW/cm^2)
| MHz | General public | Occupational |
|---|---|---|
| 0.3-1.34 | 100 | 100 (to 3 MHz) |
| 1.34-30 | 180/f^2 | 900/f^2 (3-30) |
| 30-300 | 0.2 | 1.0 |
| 300-1500 | f/1500 | f/300 |
| 1500-100000 | 1.0 | 5.0 |
OET-65 ground reflection factor 2.56 applied to S = EIRP/(4 pi d^2) by default.
