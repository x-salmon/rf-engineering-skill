# Instrument and Python tool notes

## Python libraries
| Need | Library | Starter |
|---|---|---|
| S-parameters, Smith charts, de-embedding, TDR | scikit-rf (`pip install scikit-rf`) | `skrf.Network('x.s2p').plot_s_smith()` |
| Filter design / DSP | scipy.signal | `scipy.signal.cheby1(N, rp, Wn, analog=True)` |
| Instrument control | pyvisa + pyvisa-py | `scripts/instrument.py` |
| SDR capture / demod | GNU Radio, pyrtlsdr, SoapySDR | `RtlSdr().read_samples(256*1024)` |
| Plots | matplotlib | `plt.semilogx(f, s21_db)` |
| Antenna patterns | NEC2 via PyNEC / necpp | wire models |

Before writing code against these, confirm the current API through context7. APIs change between versions.

## Resource strings
- LAN (VXI-11): `TCPIP0::192.168.1.50::INSTR`
- LAN raw socket: `TCPIP0::192.168.1.50::5025::SOCKET` (set `read_termination='\n'`)
- USB: `USB0::0x2A8D::0x1D0B::MY12345678::INSTR`
- GPIB: `GPIB0::18::INSTR`

## Common SCPI (spectrum analyzers)
| Function | Keysight X-series / R&S FSx (mostly shared) |
|---|---|
| Center / span | `:FREQ:CENT 121.5MHZ`, `:FREQ:SPAN 100KHZ` |
| RBW / VBW | `:BAND 1KHZ`, `:BAND:VID 1KHZ` |
| Ref level / atten | `:DISP:WIND:TRAC:Y:RLEV 0DBM`, `:INP:ATT 10DB` (Keysight `:POW:ATT`) |
| Detector | `:DET RMS` / `:DET POS` |
| Marker to peak | `:CALC:MARK1:MAX`, read `:CALC:MARK1:X?` `:CALC:MARK1:Y?` |
| Channel power | Keysight `:CONF:CHP`, R&S `:CALC:MARK:FUNC:POW:SEL CPOW` |
| Trace data | `:FORM ASC; :TRAC? TRACE1` (R&S `:TRAC? TRACE1` too) |
| Errors | `:SYST:ERR?` |

## Signal generators
`:FREQ 121.5MHZ`, `:POW -100DBM`, `:AM:STAT ON`, `:AM:DEPT 30`, `:OUTP ON`.
**Safety:** confirm the output goes to a load or attenuator before `:OUTP ON`. Never key into a live antenna
without authorization.

## Measurement hygiene
- Noise-like signals: RMS detector and channel power, not a peak marker
- RBW sets the displayed noise floor: DANL scales 10 log(RBW)
- Keep the mixer level about -10 to -30 dBm. Add attenuation if IMD appears; real signals do not change level when attenuation changes, internal products do
- Add the external attenuator and cable loss as a reference-level offset
