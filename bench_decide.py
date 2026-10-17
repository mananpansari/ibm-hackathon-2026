#!/usr/bin/env python3
"""#15 / Result 4: decide() latency and throughput with the MLP on zDNN (NNPA) and off.

One timed call = what the API does per withdrawal: point-in-time features from the recorded
history -> model.score() (XGBoost + Keras MLP) -> Engine.decide() (payee memory, Tether freezes,
hash-chained log). Withdrawals replay the inbound payments of the recorded test wallets, in time
order, single-threaded, with no network.

NNPA_DEVICES is read when TensorFlow loads, so on and off are two separate processes:

    python bench_decide.py --out on.json
    NNPA_DEVICES=0 python bench_decide.py --out off.json
    python bench_decide.py --compare on.json off.json

Needs C's engine.py, payee_memory.py and decision_log.py (#3/#6) next to it, plus model.py and models/ (#5).
"""
import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time

os.environ.setdefault("KERAS_BACKEND", "tensorflow")


def pct(s, p):
    return s[min(len(s) - 1, round(p / 100 * (len(s) - 1)))]


def run(args):
    import features as F
    import model
    from decision_log import DecisionLog
    from engine import MIN_USDT, Engine, FixedClock, RecordedHistories, Withdrawal
    from payee_memory import PayeeMemory, load_freezes

    import tensorflow as tf

    hist = RecordedHistories()
    ws = sorted((t["ts"], t["from"], h["address"], t["usdt"])
                for h in hist.by_addr.values() for t in h["transfers"]
                if t["to"] == h["address"] and t["from"] != h["address"] and t["usdt"] >= MIN_USDT)
    ws = ws[:: max(1, len(ws) // (args.n + args.warmup))][: args.n + args.warmup]  # spread over the whole period

    memory = PayeeMemory()
    memory.add_freezes(load_freezes())
    clock = FixedClock(0)
    log = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name
    eng = Engine(hist, memory, clock, DecisionLog(log))
    assert sorted(model._load()) == ["mlp", "xgb"], "models/ missing: the benchmark must include the MLP"

    total, scored, tiers = [], [], {}
    for i, (ts, customer, wallet, usdt) in enumerate(ws):
        t0 = time.perf_counter()
        clock.now = ts
        h = hist(wallet, ts)
        s = model.score(F.features(h, ts)) if h else None
        t1 = time.perf_counter()
        d = eng.decide(Withdrawal(customer, wallet, usdt, ts))
        t2 = time.perf_counter()
        if i >= args.warmup:
            total.append((t2 - t0) * 1000)
            scored.append((t1 - t0) * 1000)
            tiers[d.tier] = tiers.get(d.tier, 0) + 1
            assert s is not None and 0 <= s <= 1
    os.unlink(log)

    st, ss = sorted(total), sorted(scored)
    out = {
        "meta": {
            "NNPA_DEVICES": os.environ.get("NNPA_DEVICES", "(unset)"),
            "machine": platform.machine(), "cpus": os.cpu_count(),
            "nnpa_in_cpuinfo": "nnpa" in open("/proc/cpuinfo").read() if os.path.exists("/proc/cpuinfo") else False,
            "python": platform.python_version(), "tensorflow": tf.__version__,
            "ibm_zdnn_plugin": _version("ibm-zdnn-plugin"),
            "withdrawals": len(total), "warmup": args.warmup, "tiers": tiers,
        },
        "decide_p50_ms": statistics.median(st), "decide_p99_ms": pct(st, 99),
        "withdrawals_per_s": len(st) / (sum(st) / 1000),
        "score_p50_ms": statistics.median(ss), "score_p99_ms": pct(ss, 99),
    }
    print(json.dumps(out, indent=1))
    if args.out:
        json.dump(out, open(args.out, "w"), indent=1)


def _version(pkg):
    import importlib.metadata as md
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def compare(on_path, off_path):
    on, off = json.load(open(on_path)), json.load(open(off_path))
    assert str(on["meta"]["NNPA_DEVICES"]) not in ("0", "false"), "ON file was run with NNPA_DEVICES=0"
    assert str(off["meta"]["NNPA_DEVICES"]) in ("0", "false"), "OFF file was not run with NNPA_DEVICES=0"
    print("| zDNN | decide p50 ms | decide p99 ms | withdrawals/s | of which score() p50 ms |")
    print("|---|---|---|---|---|")
    for name, r in (("on", on), ("off", off)):
        print(f"| {name} | {r['decide_p50_ms']:.2f} | {r['decide_p99_ms']:.2f} | "
              f"{r['withdrawals_per_s']:.0f} | {r['score_p50_ms']:.2f} |")
    print(f"\np50 off/on = {off['decide_p50_ms'] / on['decide_p50_ms']:.2f}x")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=2000, help="timed withdrawals")
    p.add_argument("--warmup", type=int, default=100)
    p.add_argument("--out")
    p.add_argument("--compare", nargs=2, metavar=("ON_JSON", "OFF_JSON"))
    a = p.parse_args()
    sys.exit(compare(*a.compare) if a.compare else run(a))
