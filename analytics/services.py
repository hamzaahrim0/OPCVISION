from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from math import sqrt
from statistics import mean, stdev

"""
Financial formulas exposed by the analytics layer.

S-R decomposition:
    delta_AN = AN_t - AN_t-1
    performance_effect = AN_t-1 * (VL_t / VL_t-1 - 1)
    sr_effect = AN_t - AN_t-1 * (VL_t / VL_t-1)
    sr_pct = sr_effect / AN_t-1 * 100

Market concentration:
    share_i = AUM_i / total_AUM * 100
    HHI = sum(share_i ** 2) on the 0-100 percentage scale.

Risk metrics:
    periodic_return_t = VL_t / VL_t-1 - 1
    annualized_return = mean(periodic_return) * inferred_factor
    annualized_volatility = sample_std(periodic_return) * sqrt(inferred_factor)
    Sharpe = (annualized_return - risk_free_rate) / annualized_volatility
    Sortino = (annualized_return - risk_free_rate) / downside_volatility
    max_drawdown = min(VL_t / running_max(VL) - 1)
    Calmar = annualized_return / abs(max_drawdown)

Competitive score:
    each component is converted to an intra-sample percentile, then combined
    with scenario weights from SCORE_SCENARIOS and clipped to [0, 100].
"""


Number = Decimal | int | float | str


def to_decimal(value: Number | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


@dataclass(frozen=True)
class Observation:
    date: date
    isin: str
    net_assets: Decimal
    nav: Decimal


@dataclass(frozen=True)
class SREffectResult:
    isin: str
    date_t: date
    date_t1: date
    net_assets_t: Decimal
    nav_t: Decimal
    net_assets_t1: Decimal
    nav_t1: Decimal
    delta_net_assets: Decimal
    performance_effect: Decimal
    sr_effect: Decimal
    days: int
    sr_pct: Decimal


def compute_sr_effect(observations: list[Observation], max_gap_days: int | None = None) -> list[SREffectResult]:
    """
    Decompose net-asset change between consecutive observations:

    delta_AN = AN_t - AN_t-1
    performance_effect = AN_t-1 * (VL_t / VL_t-1 - 1)
    sr_effect = AN_t - AN_t-1 * (VL_t / VL_t-1)

    `sr_effect` is the implied net subscription/redemption flow. Invalid rows
    with non-positive AN or VL are excluded instead of being coerced. If
    max_gap_days is set, pairs whose observation gap exceeds that threshold are
    skipped to avoid mixing incompatible periods.
    """
    valid = [
        obs
        for obs in observations
        if obs.net_assets is not None
        and obs.nav is not None
        and obs.net_assets > 0
        and obs.nav > 0
    ]
    valid.sort(key=lambda item: (item.isin, item.date))

    results: list[SREffectResult] = []
    previous_by_isin: dict[str, Observation] = {}
    for current in valid:
        previous = previous_by_isin.get(current.isin)
        previous_by_isin[current.isin] = current
        if previous is None:
            continue
        days = (current.date - previous.date).days
        if max_gap_days is not None and days > max_gap_days:
            continue
        nav_ratio = current.nav / previous.nav
        delta = current.net_assets - previous.net_assets
        performance = previous.net_assets * (nav_ratio - Decimal("1"))
        sr = current.net_assets - previous.net_assets * nav_ratio
        results.append(
            SREffectResult(
                isin=current.isin,
                date_t=current.date,
                date_t1=previous.date,
                net_assets_t=current.net_assets,
                nav_t=current.nav,
                net_assets_t1=previous.net_assets,
                nav_t1=previous.nav,
                delta_net_assets=delta,
                performance_effect=performance,
                sr_effect=sr,
                days=days,
                sr_pct=sr / previous.net_assets * Decimal("100"),
            )
        )
    return results


@dataclass(frozen=True)
class RiskMetrics:
    isin: str
    observations: int
    annualization_factor: int | None
    annualized_return: float | None
    annualized_volatility: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    calmar: float | None
    reason: str | None = None


def infer_annualization_factor(dates: list[date]) -> int:
    gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0)
    if not gaps:
        return 252
    median_gap = gaps[len(gaps) // 2]
    return 52 if median_gap >= 5 else 252


def compute_risk_metrics(
    isin: str,
    dated_navs: list[tuple[date, Number]],
    risk_free_rate: float = 0.022,
    min_observations: int = 15,
    min_days: int = 30,
) -> RiskMetrics:
    """
    Compute annualized return/volatility, Sharpe, Sortino, max drawdown and Calmar.

    Periodic returns are r_t = VL_t / VL_t-1 - 1. Annualized return is
    mean(r_t) * factor and annualized volatility is sample_std(r_t) * sqrt(factor).
    The factor is inferred from the median observation gap: 252 for daily-like
    histories and 52 for weekly-like histories. Max drawdown is min(VL / running_max - 1).
    """
    clean = sorted(
        (d, float(nav))
        for d, nav in dated_navs
        if nav is not None and to_decimal(nav) is not None and to_decimal(nav) > 0
    )
    observations = len(clean)
    if observations < min_observations:
        return RiskMetrics(isin, observations, None, None, None, None, None, None, None, "insufficient_observations")
    if (clean[-1][0] - clean[0][0]).days < min_days:
        return RiskMetrics(isin, observations, None, None, None, None, None, None, None, "insufficient_history")

    dates = [item[0] for item in clean]
    navs = [item[1] for item in clean]
    returns = [(navs[i] / navs[i - 1]) - 1.0 for i in range(1, len(navs))]
    if len(returns) < 2:
        return RiskMetrics(isin, observations, None, None, None, None, None, None, None, "insufficient_returns")

    factor = infer_annualization_factor(dates)
    avg_return = mean(returns)
    volatility = stdev(returns)
    annualized_return = avg_return * factor
    annualized_volatility = volatility * sqrt(factor)
    sharpe = None
    if annualized_volatility > 0:
        sharpe = (annualized_return - risk_free_rate) / annualized_volatility

    downside_returns = [min(item, 0.0) for item in returns]
    downside_volatility = stdev(downside_returns) * sqrt(factor)
    sortino = None
    if downside_volatility > 0:
        sortino = (annualized_return - risk_free_rate) / downside_volatility

    running_max = navs[0]
    drawdowns = []
    for nav in navs:
        running_max = max(running_max, nav)
        drawdowns.append(nav / running_max - 1.0)
    max_drawdown = min(drawdowns)
    calmar = annualized_return / abs(max_drawdown) if max_drawdown < 0 else None

    return RiskMetrics(
        isin=isin,
        observations=observations,
        annualization_factor=factor,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=calmar,
    )


def market_structure(company_aum: dict[str, Number]) -> dict[str, object]:
    """
    Market concentration by AUM.

    share_i = AUM_i / total_AUM * 100
    HHI = sum(share_i ** 2), using percentage shares on the 0-100 scale.
    """
    clean = {name: float(value) for name, value in company_aum.items() if value is not None and float(value) > 0}
    total = sum(clean.values())
    if total <= 0:
        return {"hhi": None, "top3": None, "top5": None, "leader": None, "leader_share": None, "shares": []}
    rows = sorted(
        [{"company": name, "aum": aum, "market_share": aum / total * 100.0} for name, aum in clean.items()],
        key=lambda item: item["aum"],
        reverse=True,
    )
    return {
        "hhi": sum(item["market_share"] ** 2 for item in rows),
        "top3": sum(item["market_share"] for item in rows[:3]),
        "top5": sum(item["market_share"] for item in rows[:5]),
        "leader": rows[0]["company"],
        "leader_share": rows[0]["market_share"],
        "shares": rows,
    }


SCORE_SCENARIOS = {
    "balanced": {
        "market_share": 0.25,
        "share_gain": 0.25,
        "collection_rate": 0.20,
        "performance": 0.15,
        "estimated_revenue": 0.15,
    },
    "growth": {
        "market_share": 0.15,
        "share_gain": 0.30,
        "collection_rate": 0.30,
        "performance": 0.15,
        "estimated_revenue": 0.10,
    },
    "defensive": {
        "market_share": 0.35,
        "share_gain": 0.15,
        "collection_rate": 0.15,
        "performance": 0.20,
        "estimated_revenue": 0.15,
    },
}


def percentile_scores(values: list[float | None]) -> list[float]:
    clean = [(idx, value) for idx, value in enumerate(values) if value is not None]
    if len(clean) <= 1:
        return [50.0 for _ in values]
    ordered = sorted(clean, key=lambda item: item[1])
    scores = [50.0 for _ in values]
    denominator = len(ordered) - 1
    for rank, (idx, _) in enumerate(ordered):
        scores[idx] = rank / denominator * 100.0
    return scores


def competitive_scores(rows: list[dict[str, object]], scenario: str = "balanced") -> list[dict[str, object]]:
    weights = SCORE_SCENARIOS.get(scenario, SCORE_SCENARIOS["balanced"])
    scored = [dict(row) for row in rows]
    component_scores = {
        metric: percentile_scores([row.get(metric) for row in scored])
        for metric in weights
    }
    for index, row in enumerate(scored):
        score = 0.0
        for metric, weight in weights.items():
            component = component_scores[metric][index]
            row[f"score_{metric}"] = component
            score += component * weight
        row["score"] = max(0.0, min(100.0, score))
        row["profile"] = strategic_profile(row)
        row["priority"] = priority(row)
        row["recommendation"] = recommendation(row)
    return sorted(scored, key=lambda item: ({"High": 0, "Medium": 1, "Monitor": 2}[item["priority"]], -item["score"]))


def strategic_profile(row: dict[str, object]) -> str:
    share_gain = row.get("share_gain")
    collection_rate = row.get("collection_rate")
    if share_gain is None or collection_rate is None:
        return "To qualify"
    if share_gain >= 0 and collection_rate >= 0:
        return "Acceleration"
    if share_gain >= 0 and collection_rate < 0:
        return "Share gain with outflows"
    if share_gain < 0 and collection_rate >= 0:
        return "Inflows without relative gain"
    return "Competitive pressure"


def priority(row: dict[str, object]) -> str:
    if row["profile"] == "Acceleration" and row["score"] >= 65:
        return "High"
    if row["profile"] == "Competitive pressure" and (row.get("market_share", 0) >= 3 or row.get("sr_effect", 0) < -500_000_000):
        return "High"
    if abs(row.get("share_gain") or 0) >= 0.10 or abs(row.get("collection_rate") or 0) >= 5 or row["score"] >= 60:
        return "Medium"
    return "Monitor"


def recommendation(row: dict[str, object]) -> str:
    if row["profile"] == "Acceleration" and row["score"] >= 65:
        return "Identify repeatable performance and distribution drivers."
    if row["profile"] == "Competitive pressure" and row.get("market_share", 0) >= 3:
        return "Prioritize a commercial diagnostic on flows, fees and network coverage."
    if row["profile"] == "Inflows without relative gain":
        return "Clarify positioning: peers are growing faster despite positive collection."
    if row["profile"] == "Share gain with outflows":
        return "Check whether redemptions are temporary or class-specific."
    return "Maintain monitoring and re-score next period."


def stale_bucket(as_of: date, snapshot_date: date | None) -> str:
    if snapshot_date is None:
        return "missing"
    age = (as_of - snapshot_date).days
    if age <= 7:
        return "fresh"
    if age <= 31:
        return "watch"
    return "stale"
