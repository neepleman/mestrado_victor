#!/usr/bin/env python3
"""Reanalysis of the paired tractor recordings (article Sections 4.1-4.5).

Reproduces, from the files in data/:
  4.1  frame-sequence agreement between the prototype log and the PCAN-View trace
  4.2  independent recalculation of three SAE J1939 signals from raw payloads
  4.3  comparison of paired inter-frame intervals (raw recordings and derived CSV)
  4.4  accounting of decoded output records
  4.5  laboratory benchmark summary
and writes Figures 2 and 3.

Usage (from the repository root):
    python3 analysis/reanalysis.py

Outputs are written to analysis/results/. Only the Python standard library is
needed for the numerical results; matplotlib is needed for the figures.
"""

import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = Path(__file__).resolve().parent / "results"

REF_TRACE = DATA / "raw" / "pcan_john_deere_log.trc"
PROTO_RAW = DATA / "raw" / "tracktor_john_deere_log.csv"
DECODED = DATA / "processed" / "decoded.csv"
DERIVED_DT = DATA / "processed" / "comparacao_deltat.csv"
BENCH_INPUT = DATA / "bench" / "kuhn_accura_replay_input.txt"
BENCH_RAW = DATA / "bench" / "raw_2026-04-06_17-04-28.csv"
BENCH_METRICS = DATA / "bench" / "metricas_artigo.csv"

ALIGN_K = 100                                   # Algorithm 1, alignment length
ANCHOR = ("0CFFFF1C", 8, "5250703D2043D91A")    # Algorithm 1, anchor frame
TOL = 1e-9                                      # Section 3.3, numerical tolerance

# Section 3.3: (decoded-export name, PGN, function(payload bytes) -> engineering value)
SIGNALS = [
    ("Engine Speed", 61444, lambda b: int.from_bytes(b[3:5], "little") * 0.125, "rpm"),
    ("Actual Engine - Percent Torque", 61444, lambda b: b[2] * 1 - 125, "%"),
    ("Engine Fuel Rate", 65266, lambda b: int.from_bytes(b[0:2], "little") * 0.05, "L/h"),
]


# ----------------------------------------------------------------------------- helpers
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quantile(sorted_values, p):
    """Linear interpolation between closest ranks (same as numpy's default)."""
    h = (len(sorted_values) - 1) * p
    i = math.floor(h)
    j = min(i + 1, len(sorted_values) - 1)
    return sorted_values[i] + (h - i) * (sorted_values[j] - sorted_values[i])


def pgn_of(can_id_hex):
    """SAE J1939 PGN from a 29-bit identifier (PDU1: PS excluded; PDU2: PS included)."""
    can_id = int(can_id_hex, 16)
    edp_dp = (can_id >> 24) & 0x3
    pf = (can_id >> 16) & 0xFF
    ps = (can_id >> 8) & 0xFF
    return (edp_dp << 16) | (pf << 8) | (ps if pf >= 240 else 0)


def hms_to_ms(text):
    h, m, s = text.split(":")
    return (int(h) * 3600 + int(m) * 60 + float(s)) * 1000.0


def comma_float(text):
    return float(text.replace(",", "."))


# ----------------------------------------------------------------------------- parsing
def read_reference(path):
    """PCAN-View trace v2.0: returns (data_frames, status_record_count).

    Each data frame: dict(n=trace number, t=offset ms, sig=(ID, DLC, PAYLOAD)).
    """
    frames, status = [], 0
    with open(path, encoding="latin-1") as f:
        for line in f:
            if line.startswith(";") or not line.strip():
                continue
            p = line.split()
            kind = p[2]
            if kind == "DT":
                dlc = int(p[5])
                payload = "".join(p[6:6 + dlc]).upper()
                frames.append({"n": int(p[0]), "t": float(p[1]),
                               "sig": (p[3].upper(), dlc, payload)})
            else:
                status += 1
    return frames, status


def read_prototype(path):
    frames = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            frames.append({"t": hms_to_ms(r["Timestamp"]), "ts": r["Timestamp"],
                           "sig": (r["ID_HEX"].upper(), int(r["DLC"]), r["DADOS_HEX"].upper())})
    return frames


def read_decoded(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


# ----------------------------------------------------------------------------- 4.1
def frame_agreement(ref, proto):
    rsig = [f["sig"] for f in ref]
    psig = [f["sig"] for f in proto]

    anchor_ref = [i for i, s in enumerate(rsig) if s == ANCHOR]
    anchor_proto = [i for i, s in enumerate(psig) if s == ANCHOR]

    head = psig[:ALIGN_K]
    starts = [s for s in range(len(rsig) - ALIGN_K + 1) if rsig[s:s + ALIGN_K] == head]
    if len(starts) != 1:
        raise SystemExit(f"Alignment not unique: {starts}")
    s = starts[0]
    n = len(psig)
    if s + n > len(rsig):
        raise SystemExit("Reference segment shorter than prototype recording")

    mismatches = [i for i in range(n) if psig[i] != rsig[s + i]]
    seg = ref[s:s + n]
    return {
        "anchor_index_reference_0based": anchor_ref,
        "anchor_index_prototype_0based": anchor_proto,
        "reference_start_0based": s,
        "reference_trace_number_first": seg[0]["n"],
        "reference_trace_number_last": seg[-1]["n"],
        "compared_frames": n,
        "mismatch_count": len(mismatches),
        "mismatch_locations": mismatches,
        "reference_frames_before": s,
        "reference_frames_after": len(rsig) - (s + n),
        "reference_span_s": round((seg[-1]["t"] - seg[0]["t"]) / 1000.0, 6),
        "prototype_span_s": round((proto[-1]["t"] - proto[0]["t"]) / 1000.0, 6),
        "distinct_identifiers": len({x[0] for x in psig}),
        "distinct_pgns": len({pgn_of(x[0]) for x in psig}),
    }, s


# ----------------------------------------------------------------------------- 4.2
def signal_checks(proto, decoded):
    results = []
    series = {}
    for name, pgn, conv, unit in SIGNALS:
        raw = [f for f in proto if pgn_of(f["sig"][0]) == pgn]
        exp = [r for r in decoded if r["PGN_Nome"] == name]
        if len(raw) != len(exp):
            raise SystemExit(f"{name}: {len(raw)} raw frames vs {len(exp)} exported values")
        ts_mismatch = sum(1 for a, b in zip(raw, exp) if a["ts"] != b["Timestamp"])
        recalculated = [conv(bytes.fromhex(f["sig"][2])) for f in raw]
        exported = [float(r["Valor"]) for r in exp]
        diffs = [abs(a - b) for a, b in zip(recalculated, exported)]
        results.append({
            "signal": name, "pgn": pgn, "unit": unit,
            "values_compared": len(exp),
            "timestamp_mismatches": ts_mismatch,
            "max_abs_difference": max(diffs),
            "all_within_tolerance": all(d <= TOL for d in diffs),
            "min_value": min(exported), "max_value": max(exported),
        })
        series[name] = ([f["t"] for f in raw], exported, unit)
    return results, series


# ----------------------------------------------------------------------------- 4.3
def interval_comparison(ref, proto, s):
    n = len(proto)
    seg = ref[s:s + n]
    d = [(proto[i]["t"] - proto[i - 1]["t"]) - (seg[i]["t"] - seg[i - 1]["t"])
         for i in range(1, n)]
    a = sorted(abs(x) for x in d)
    excursions = [{"pair_index": i, "difference_ms": round(d[i - 1], 3),
                   "pgn": pgn_of(proto[i]["sig"][0]), "identifier": proto[i]["sig"][0]}
                  for i in range(1, n) if d[i - 1] > 100]
    below = sum(1 for x in a if x < 1.0)
    res = {
        "paired_intervals": len(d),
        "abs_below_1ms": below,
        "abs_below_1ms_percent": round(100.0 * below / len(d), 2),
        "median_abs_ms": round(quantile(a, 0.5), 3),
        "p99_abs_ms": round(quantile(a, 0.99), 3),
        "positive_excursions_above_100ms": excursions,
    }

    # Derived CSV produced during the dissertation (decimal comma, ';' separator)
    with open(DERIVED_DT, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    if len(rows) != len(d):
        raise SystemExit(f"Derived CSV has {len(rows)} rows, expected {len(d)}")
    ref_raw = [seg[i]["t"] - seg[i - 1]["t"] for i in range(1, n)]
    proto_raw = [proto[i]["t"] - proto[i - 1]["t"] for i in range(1, n)]
    ref_csv = [comma_float(r["DeltaT_PCAN"]) for r in rows]
    proto_csv = [comma_float(r["DeltaT_Proto"]) for r in rows]
    ref_diff = [abs(x - y) for x, y in zip(ref_csv, ref_raw)]
    proto_diff = [abs(x - y) for x, y in zip(proto_csv, proto_raw)]
    d_csv = [p - r for p, r in zip(proto_csv, ref_csv)]
    below_csv = sum(1 for x in d_csv if abs(x) < 1.0)
    res["derived_csv"] = {
        "abs_below_1ms_percent": round(100.0 * below_csv / len(d_csv), 2),
        "reference_positions_differing_from_raw": sum(1 for x in ref_diff if x > 1e-6),
        "reference_max_abs_discrepancy_ms": round(max(ref_diff), 3),
        "prototype_positions_differing_from_raw": sum(1 for x in proto_diff if x > 1e-6),
        "excursions_above_100ms": sorted(round(x, 3) for x in d_csv if x > 100),
    }
    return res, d, seg


# ----------------------------------------------------------------------------- 4.4
def decoded_accounting(decoded):
    names = [r["PGN_Nome"] for r in decoded]
    return {
        "records_total": len(decoded),
        "records_named": sum(1 for x in names if x.strip()),
        "records_unnamed": sum(1 for x in names if not x.strip()),
        "literal_UD_values": sum(1 for r in decoded if r["Valor"].strip() == "UD"),
        "selected_signal_records": {n: names.count(n) for n, *_ in SIGNALS},
    }


# ----------------------------------------------------------------------------- 4.5
def bench_summary():
    with open(BENCH_INPUT) as f:
        inp = [line.split() for line in f if line.strip()]
    in_t = [float(x[0].strip("()")) for x in inp]
    in_sig = [x[2].upper().replace("#", ",") for x in inp]

    with open(BENCH_RAW, newline="") as f:
        rx = [f"{r['ID_HEX'].upper()},{r['DADOS_HEX'].upper()}" for r in csv.DictReader(f)]

    # In-order matching of received frames against the replay input
    j = matched = 0
    for frame in rx:
        k = j
        while k < len(in_sig) and in_sig[k] != frame:
            k += 1
        if k < len(in_sig):
            matched += 1
            j = k + 1
    in_set = set(in_sig)

    with open(BENCH_METRICS, newline="") as f:
        m = list(csv.DictReader(f))
    dec = sorted(float(r["Tempo_Decod_ms"]) for r in m)
    return {
        "input_frames": len(in_sig),
        "input_span_s": round(in_t[-1] - in_t[0], 2),
        "received_frames": len(rx),
        "received_frames_not_in_input": sum(1 for x in rx if x not in in_set),
        "received_frames_matched_in_order": matched,
        "input_frames_not_observed": len(in_sig) - matched,
        "metric_samples_1s": len(m),
        "decode_ms_mean": round(statistics.mean(dec), 3),
        "decode_ms_median": round(quantile(dec, 0.5), 3),
        "decode_ms_p90": round(quantile(dec, 0.9), 3),
        "decode_ms_p95": round(quantile(dec, 0.95), 3),
        "decode_ms_p99": round(quantile(dec, 0.99), 3),
        "decode_ms_max": round(dec[-1], 3),
        "queue_peak": max(int(r["Fila_UI"]) for r in m),
        "final_rx_counter": int(m[-1]["Total_Rx"]),
    }


# ----------------------------------------------------------------------------- figures
def make_figures(d, seg, proto, series):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: figures skipped")
        return

    # Figure 2
    t0 = seg[0]["t"]
    x = [(seg[i]["t"] - t0) / 1000.0 for i in range(1, len(seg))]
    a = sorted(abs(v) for v in d)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    ax1.plot(x, d, ".", ms=2, color="#2b6cb0")
    for i, v in enumerate(d):
        if v > 100:
            ax1.annotate(f"PGN {pgn_of(proto[i + 1]['sig'][0])}\n{v:.1f} ms", (x[i], v),
                         textcoords="offset points", xytext=(5, -5), fontsize=8)
    ax1.set_xlabel("Elapsed time in reference recording (s)")
    ax1.set_ylabel("Prototype − reference interval (ms)")
    ax1.set_title("A", loc="left", fontweight="bold")
    pos = [v for v in a if v > 0]
    ax2.step(pos, [(i + 1 + (len(a) - len(pos))) / len(a) for i in range(len(pos))],
             where="post", color="#2b6cb0")
    ax2.axvline(1.0, ls="--", color="gray")
    ax2.set_xscale("log")
    ax2.set_xlabel("Absolute interval difference (ms)")
    ax2.set_ylabel("Cumulative proportion")
    ax2.set_title("B", loc="left", fontweight="bold")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"figure2_interval_differences.{ext}", dpi=300)
    plt.close(fig)

    # Figure 3
    p0 = proto[0]["t"]
    fig, axes = plt.subplots(3, 1, figsize=(8, 7), sharex=True)
    for ax, (name, (t, v, unit)) in zip(axes, series.items()):
        ax.plot([(ti - p0) / 1000.0 for ti in t], v, lw=0.8, color="#2b6cb0")
        ax.set_ylabel(f"{name}\n({unit})", fontsize=8)
    axes[-1].set_xlabel("Elapsed time in prototype recording (s)")
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"figure3_signal_time_series.{ext}", dpi=300)
    plt.close(fig)


# ----------------------------------------------------------------------------- main
def main():
    OUT.mkdir(exist_ok=True)
    inputs = [REF_TRACE, PROTO_RAW, DECODED, DERIVED_DT, BENCH_INPUT, BENCH_RAW, BENCH_METRICS]

    ref, status = read_reference(REF_TRACE)
    proto = read_prototype(PROTO_RAW)
    decoded = read_decoded(DECODED)

    s41, s = frame_agreement(ref, proto)
    s41 = {"reference_data_frames": len(ref), "reference_status_records": status,
           "prototype_data_frames": len(proto), **s41}
    s42, series = signal_checks(proto, decoded)
    s43, d, seg = interval_comparison(ref, proto, s)
    s44 = decoded_accounting(decoded)
    s45 = bench_summary()

    results = {
        "input_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in inputs},
        "4.1_frame_agreement": s41,
        "4.2_signal_checks": s42,
        "4.3_interval_comparison": s43,
        "4.4_decoded_accounting": s44,
        "4.5_laboratory_benchmark": s45,
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    make_figures(d, seg, proto, series)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
