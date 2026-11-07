#!/usr/bin/env python3
"""DSA comparison experiment: rotation draw vs backtracking draw.

The rotation draw shuffles members into a circle (O(n) per attempt, retries
while a banned pair sits in the circle). Backtracking search finds a full
derangement honoring every ban (worst-case exponential, pruned in practice).

The experiment measures, for n in {10, 25, 50, 100, 200} members and
exclusion density d in {0, 0.05, 0.1, 0.2} of all ordered pairs:
  - success rate over 40 draws per point (rotation is randomized and may
    fail after 50 tries; backtracking succeeds unless the instance is
    infeasible);
  - median wall-clock time of a successful draw.

Results: a table printed to stdout and a plot saved to
../proposal/dsa_bench.png (time vs n for both algorithms, plus the
rotation success rate). Run from the app/ directory:

    python3 bench.py
"""
import statistics
import sys
import time
from random import Random

from dsa import HashTable, draw_backtracking, draw_rotation

SIZES = [10, 25, 50, 100, 200]
DENSITIES = [0.0, 0.05, 0.1, 0.2]
RUNS = 40
TRIES = 50


def make_banned(members, density, rng):
    """Random exclusions: density * n ordered pairs, never self-pairs."""
    banned = HashTable()
    n = len(members)
    pairs = max(1, int(density * n)) if density else 0
    for _ in range(pairs):
        a, b = rng.sample(members, 2)
        s = banned.get(a)
        if s is None:
            s = set()
            banned.set(a, s)
        s.add(b)
    return banned


def is_feasible(members, banned):
    """A draw exists: no member is banned by more than n-2 others."""
    n = len(members)
    for u in members:
        if len(banned.get(u, ()) or ()) >= n - 1:
            return False
    return True


def timeit(fn):
    t0 = time.perf_counter()
    res = fn()
    dt = (time.perf_counter() - t0) * 1000
    return res, dt


def main():
    rng = Random(2026)
    print(f"{'n':>5} {'density':>8} | {'rotation ok':>11} {'rot ms':>9} | "
          f"{'backtrack ok':>12} {'bt ms':>9}")
    rows = []
    for n in SIZES:
        members = list(range(n))
        for d in DENSITIES:
            rot_ok = bt_ok = 0
            rot_ms, bt_ms = [], []
            for run in range(RUNS):
                banned = make_banned(members, d, rng)
                if not is_feasible(members, banned):
                    continue
                p, ms = timeit(lambda: draw_rotation(members, banned, rng, tries=TRIES))
                if p is not None:
                    rot_ok += 1
                    rot_ms.append(ms)
                p, ms = timeit(lambda: draw_backtracking(members, banned))
                if p is not None:
                    bt_ok += 1
                    bt_ms.append(ms)
            rot_rate, bt_rate = rot_ok / RUNS, bt_ok / RUNS
            rot_med = statistics.median(rot_ms) if rot_ms else float("nan")
            bt_med = statistics.median(bt_ms) if bt_ms else float("nan")
            rows.append((n, d, rot_rate, rot_med, bt_rate, bt_med))
            print(f"{n:>5} {d:>8} | {rot_rate:>10.0%} {rot_med:>8.3f} | "
                  f"{bt_rate:>11.0%} {bt_med:>8.3f}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nmatplotlib not installed — plot skipped")
        return 0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    colors = {0.0: "#2f9e6e", 0.05: "#e3b341", 0.1: "#e07b39", 0.2: "#d64545"}

    # time vs n (density 0.1): both algorithms
    for d, ls, marker in [(0.0, "-", "o"), (0.1, "--", "s")]:
        xs = [n for (n, dd, *_) in rows if dd == d]
        y_rot = [r[3] for r in rows if r[1] == d]
        y_bt = [r[5] for r in rows if r[1] == d]
        ax1.plot(xs, y_rot, ls, marker=marker, color="#2f9e6e",
                 label=f"rotation, density {d}")
        ax1.plot(xs, y_bt, ls, marker=marker, color="#d64545",
                 label=f"backtracking, density {d}")
    ax1.set_xscale("log"); ax1.set_yscale("log")
    ax1.set_xlabel("group size n"); ax1.set_ylabel("median time, ms")
    ax1.set_title("Draw time vs group size")
    ax1.legend(fontsize=8); ax1.grid(alpha=.3)

    # rotation success rate vs density
    for n in SIZES:
        xs = [d for (nn, d, *_) in rows if nn == n]
        ys = [r[2] for r in rows if r[0] == n]
        ax2.plot(xs, ys, marker="o", label=f"n = {n}")
    ax2.set_xlabel("exclusion density (share of banned pairs)")
    ax2.set_ylabel("rotation success rate, 50 tries")
    ax2.set_title("When the O(n) rotation stops coping")
    ax2.set_ylim(-0.03, 1.03); ax2.legend(fontsize=8); ax2.grid(alpha=.3)

    fig.suptitle("Secret Santa draw: rotation vs backtracking", y=1.02)
    fig.tight_layout()
    out = "../proposal/dsa_bench.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print(f"\nplot saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
