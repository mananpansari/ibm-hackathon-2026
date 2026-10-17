"""Append-only, hash-chained JSONL decision log (issue #3).

Each line is {"prev": <hash of the line before>, "hash": <sha256 of this entry>, ...record}.
Editing, reordering or deleting any past line breaks the chain, and verify() names the first
broken line. Dropping lines from the end can't be seen from the file alone; keep the last hash
somewhere else (the officer page, a daily print) if that matters.

    python decision_log.py   # self-check: a clean log verifies, any edit is caught
"""
import hashlib
import json
from pathlib import Path

GENESIS = "0" * 64


def _digest(entry):
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class DecisionLog:
    def __init__(self, path):
        self.path = Path(path)
        self.last = GENESIS
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self.last = json.loads(line)["hash"]

    def append(self, record):
        """Writes one record (a JSON-able dict) and returns its hash."""
        entry = {"prev": self.last, **record}
        entry["hash"] = _digest(entry)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        self.last = entry["hash"]
        return entry["hash"]


def verify(path):
    """None if every line chains correctly, else the 1-based number of the first bad line."""
    prev = GENESIS
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return n
        if entry.get("prev") != prev or entry.get("hash") != _digest(entry):
            return n
        prev = entry["hash"]
    return None


def _self_check():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "log.jsonl"
        log = DecisionLog(path)
        for i in range(5):
            log.append({"i": i, "tier": "release", "amount": 100.0 * i})
        assert verify(path) is None
        DecisionLog(path).append({"i": 5})  # reopening continues the chain
        assert verify(path) is None
        good = path.read_text().splitlines()

        def check(lines, bad_line):
            path.write_text("\n".join(lines) + "\n")
            assert verify(path) == bad_line, (verify(path), bad_line)

        edited = json.loads(good[2])
        edited["amount"] = 1.0
        check(good[:2] + [json.dumps(edited)] + good[3:], 3)  # edit a field
        edited["hash"] = _digest(edited)
        check(good[:2] + [json.dumps(edited)] + good[3:], 4)  # re-hash it: the next line breaks
        check(good[:1] + good[2:], 2)                          # delete a line
        check([good[1], good[0]] + good[2:], 1)                # reorder
        check(good[:3] + ["not json"] + good[4:], 4)
    print("self-check passed: decision log chains and catches tampering")


if __name__ == "__main__":
    _self_check()
