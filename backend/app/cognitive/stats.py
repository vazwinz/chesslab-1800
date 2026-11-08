"""Small, dependency-free statistics helpers (Wilson intervals, OLS with prediction intervals,
bootstrap). Kept here so every uncertainty number in the app has one documented source."""
from __future__ import annotations

import math
import random
import statistics

# two-sided 95% Student-t critical values
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t95(df: int) -> float:
    if df <= 0:
        return float("inf")
    keys = sorted(_T95)
    for k in keys:
        if df <= k:
            return _T95[k]
    return 1.96


def wilson(ok: int, n: int, z: float = 1.96) -> dict:
    if n == 0:
        return {"rate": None, "low": None, "high": None, "n": 0}
    p = ok / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"rate": round(p, 4), "low": round(max(0, c - h), 4), "high": round(min(1, c + h), 4), "n": n}


def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def mean_ci(xs: list[float]) -> dict:
    n = len(xs)
    if n == 0:
        return {"mean": None, "low": None, "high": None, "n": 0}
    m = statistics.fmean(xs)
    if n == 1:
        return {"mean": m, "low": None, "high": None, "n": 1}
    se = statistics.stdev(xs) / math.sqrt(n)
    t = t95(n - 1)
    return {"mean": round(m, 3), "low": round(m - t * se, 3), "high": round(m + t * se, 3), "n": n}


def ols(xs: list[float], ys: list[float]) -> dict | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    icpt = my - slope * mx
    resid = [y - (icpt + slope * x) for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in resid) / (n - 2)
    se_slope = math.sqrt(s2 / sxx)
    t = t95(n - 2)
    return {"slope": slope, "intercept": icpt, "s2": s2, "sxx": sxx, "mx": mx, "n": n,
            "slope_low": slope - t * se_slope, "slope_high": slope + t * se_slope}


def predict(fit: dict, x: float) -> dict:
    """Point forecast with a 95% *prediction* interval (where a new observation may land)."""
    t = t95(fit["n"] - 2)
    y = fit["intercept"] + fit["slope"] * x
    se = math.sqrt(fit["s2"] * (1 + 1 / fit["n"] + (x - fit["mx"]) ** 2 / fit["sxx"]))
    se_mean = math.sqrt(fit["s2"] * (1 / fit["n"] + (x - fit["mx"]) ** 2 / fit["sxx"]))
    return {"x": x, "value": y, "pi_low": y - t * se, "pi_high": y + t * se,
            "trend_low": y - t * se_mean, "trend_high": y + t * se_mean}


def bootstrap_diff(a: list[float], b: list[float], iters: int = 2000, seed: int = 7) -> dict | None:
    """95% bootstrap CI for mean(b) - mean(a)."""
    if len(a) < 3 or len(b) < 3:
        return None
    rng = random.Random(seed)
    diffs = []
    for _ in range(iters):
        sa = [rng.choice(a) for _ in a]
        sb = [rng.choice(b) for _ in b]
        diffs.append(statistics.fmean(sb) - statistics.fmean(sa))
    diffs.sort()
    return {"diff": statistics.fmean(b) - statistics.fmean(a), "low": diffs[int(0.025 * iters)],
            "high": diffs[int(0.975 * iters) - 1]}
