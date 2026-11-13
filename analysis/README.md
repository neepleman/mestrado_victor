# Reanalysis of the paired tractor recordings

`reanalysis.py` reproduces the results reported in Sections 4.1–4.5 of the article
*"Evaluation of a passive SAE J1939 acquisition platform using a commercial reference"*
from the files in [`../data/`](../data/), and generates Figures 2 and 3.

## Running

From the repository root:

```bash
pip install -r analysis/requirements.txt   # matplotlib, only needed for the figures
python3 analysis/reanalysis.py
```

The numerical results need only the Python standard library (tested with Python 3.13).
Outputs are written to `analysis/results/`:

| File | Content |
|---|---|
| `results.json` | All numerical results, grouped by article section, plus SHA-256 of every input file. |
| `figure2_interval_differences.png/.pdf` | Figure 2: signed inter-frame interval differences (A) and ECDF of absolute differences (B). |
| `figure3_signal_time_series.png/.pdf` | Figure 3: engine speed, actual engine percent torque and engine fuel rate. |

## Input files and checksums

`SHA256SUMS` lists the SHA-256 checksum of each input file. To verify them:

```bash
cd data && sha256sum -c ../analysis/SHA256SUMS
```

## What the script does

| Article section | Procedure |
|---|---|
| 4.1 Frame agreement | Parses the PCAN-View trace (data frames only; status records counted separately) and the prototype raw log. Each frame is represented by the signature (complete identifier, DLC, payload). The prototype start is located in the reference by requiring an exact match of its first 100 signatures (Algorithm 1); all prototype signatures are then compared position by position. Reports frames before/after the aligned interval, the time spans, and the numbers of distinct identifiers and PGNs. |
| 4.2 Signal checks | Recalculates engine speed (PGN 61444, bytes 4–5, little-endian, × 0.125 rpm), actual engine percent torque (PGN 61444, byte 3, − 125 %) and engine fuel rate (PGN 65266, bytes 1–2, little-endian, × 0.05 L/h) directly from the raw payloads, and compares them in order with the values in `decoded.csv` (tolerance 10⁻⁹). Timestamps are compared as well. |
| 4.3 Interval comparison | For each pair of consecutive aligned frames, computes (prototype interval − reference interval) in ms. Reports the share of absolute differences below 1 ms, the median and 99th percentile (linear interpolation), and the positive differences above 100 ms. Repeats the comparison using the intervals stored in `comparacao_deltat.csv` and reports where that file departs from the raw recordings. |
| 4.4 Decoded output | Counts records, named and unnamed records, literal `UD` values and the records of the three checked signals in `decoded.csv`. |
| 4.5 Laboratory benchmark | Compares the replay input with the frames recorded by the Pi (frames not present in the input; in-order matches; input frames not observed) and summarizes the per-second decoding-time samples in `metricas_artigo.csv`. |

PGNs are derived from the 29-bit identifier following SAE J1939: for PDU1 messages (PF < 240) the
PDU-specific byte is excluded; for PDU2 messages it is included.
