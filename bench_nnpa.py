#!/usr/bin/env python3
"""NNPA on/off benchmark for a Keras MLP on IBM LinuxONE (s390x).

NNPA_DEVICES must be set BEFORE TensorFlow is imported, so run this script twice,
as two separate processes:

    python bench_nnpa.py --out results_on.json                   # accelerator on (default)
    NNPA_DEVICES=0 python bench_nnpa.py --out results_off.json   # accelerator off
    python bench_nnpa.py --compare results_on.json results_off.json

Notes (from IBM's "IBM Z Accelerated for TensorFlow" README):
  * Only graph execution is accelerated, so inference runs inside a tf.function.
  * Some ops are left on the CPU when the accelerator overhead would outweigh the gain,
    so tiny models and tiny batches may show little or no speed-up. Report what you measure.
  * Do not set ZDNN_ENABLE_PRECHECK / verbose TF logging while benchmarking (they slow it down).
"""
import argparse
import json
import os
import sys
import time


def run(args):
    import numpy as np

    os.environ.setdefault("KERAS_BACKEND", "tensorflow")
    import importlib.metadata as md

    import tensorflow as tf
    from tensorflow import keras

    try:
        plugin = md.version("ibm-zdnn-plugin")
    except Exception:
        plugin = None

    meta = {
        "NNPA_DEVICES": os.environ.get("NNPA_DEVICES", "(unset)"),
        "tensorflow": tf.__version__,
        "ibm_zdnn_plugin": plugin,
        "features": args.features,
        "hidden": args.hidden,
        "physical_devices": [d.name for d in tf.config.list_physical_devices()],
    }
    print("meta:", json.dumps(meta))

    rng = np.random.default_rng(0)
    layers = [keras.layers.Input((args.features,))]
    layers += [keras.layers.Dense(h, activation="relu") for h in args.hidden]
    layers += [keras.layers.Dense(1, activation="sigmoid")]
    model = keras.Sequential(layers)
    infer = tf.function(lambda x: model(x, training=False))  # graph mode is required

    results = []
    for b in args.batches:
        x = tf.constant(rng.standard_normal((b, args.features)).astype("float32"))
        for _ in range(args.warmup):
            infer(x).numpy()

        lat = []
        t_start = time.perf_counter()
        while True:
            t0 = time.perf_counter()
            infer(x).numpy()  # .numpy() forces completion before we stop the clock
            lat.append((time.perf_counter() - t0) * 1000.0)
            elapsed = time.perf_counter() - t_start
            if len(lat) >= args.iters or (elapsed >= args.max_seconds and len(lat) >= 20):
                break

        s = sorted(lat)

        def pct(p):
            return s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))]

        row = {
            "batch": b,
            "calls": len(lat),
            "p50_ms": pct(50),
            "p99_ms": pct(99),
            "rows_per_s": b * len(lat) / (sum(lat) / 1000.0),
        }
        results.append(row)
        print(
            f"batch {b:>5}: p50 {row['p50_ms']:.3f} ms  p99 {row['p99_ms']:.3f} ms  "
            f"{row['rows_per_s']:.0f} rows/s  ({row['calls']} calls)"
        )

    out = {"meta": meta, "results": results}
    if args.out:
        with open(args.out, "w") as f:
            json.dump(out, f, indent=2)
        print("wrote", args.out)


def compare(path_on, path_off):
    on = json.load(open(path_on))
    off = json.load(open(path_off))
    print(f"ON  run: NNPA_DEVICES={on['meta']['NNPA_DEVICES']}  plugin={on['meta']['ibm_zdnn_plugin']}")
    print(f"OFF run: NNPA_DEVICES={off['meta']['NNPA_DEVICES']}")
    if str(on["meta"]["NNPA_DEVICES"]).lower() in ("0", "false"):
        print("WARNING: the ON file was produced with NNPA_DEVICES=0.")
    if str(off["meta"]["NNPA_DEVICES"]).lower() not in ("0", "false"):
        print("WARNING: the OFF file was NOT produced with NNPA_DEVICES=0.")

    print(
        f"\n{'batch':>6} | {'p50 on':>9} {'p50 off':>9} {'speedup':>8} | "
        f"{'p99 on':>9} {'p99 off':>9} | {'rows/s on':>10} {'rows/s off':>10}"
    )
    speedups = []
    for a, c in zip(on["results"], off["results"]):
        sp = c["p50_ms"] / a["p50_ms"]
        speedups.append(sp)
        print(
            f"{a['batch']:>6} | {a['p50_ms']:>9.3f} {c['p50_ms']:>9.3f} {sp:>7.2f}x | "
            f"{a['p99_ms']:>9.3f} {c['p99_ms']:>9.3f} | "
            f"{a['rows_per_s']:>10.0f} {c['rows_per_s']:>10.0f}"
        )
    if speedups and all(0.9 <= v <= 1.1 for v in speedups):
        print(
            "\nNOTE: no measurable difference at any batch size. The accelerator path may not be active "
            "or the ops were not remapped. Check with TF_CPP_MIN_LOG_LEVEL=0 TF_CPP_VMODULE='remapper=1' "
            "and ZDNN_ENABLE_PRECHECK=true on a short run, or try wider layers / larger batches."
        )


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=None, help="write results JSON here")
    p.add_argument("--compare", nargs=2, metavar=("ON_JSON", "OFF_JSON"))
    p.add_argument("--features", type=int, default=32)
    p.add_argument("--hidden", type=int, nargs="+", default=[512, 256, 128])
    p.add_argument("--batches", type=int, nargs="+", default=[1, 32, 256, 1024, 4096])
    p.add_argument("--iters", type=int, default=200)
    p.add_argument("--warmup", type=int, default=20)
    p.add_argument("--max-seconds", type=float, default=5.0, help="time budget per batch size")
    args = p.parse_args()

    if args.compare:
        compare(*args.compare)
    else:
        run(args)


if __name__ == "__main__":
    sys.exit(main())
