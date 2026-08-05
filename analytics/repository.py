from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Max, OuterRef, Q, Subquery, Sum

from analytics.services import (
    Observation,
    competitive_scores,
    compute_sr_effect,
    compute_risk_metrics,
    market_structure,
    percentile_scores,
    stale_bucket,
)
from funds.models import Fund, FundPerformanceSnapshot


def parse_date_param(value: str | None, fallback: date | None = None) -> date | None:
    if not value:
        return fallback
    return date.fromisoformat(value)


def plain_params(params) -> dict[str, str]:
    if not params:
        return {}
    if hasattr(params, "items"):
        return {key: value for key, value in params.items() if value not in (None, "")}
    return dict(params)


def latest_available_date() -> date | None:
    return FundPerformanceSnapshot.objects.aggregate(value=Max("date"))["value"]


def filtered_funds(params) -> Q:
    params = plain_params(params)
    query = Q()
    if params.get("management_company"):
        query &= Q(fund__management_company__name__icontains=params["management_company"])
    if params.get("classification"):
        query &= Q(fund__classification=params["classification"])
    if params.get("subscriber_type"):
        query &= Q(fund__subscriber_type=params["subscriber_type"])
    return query


def filtered_fund_query(params) -> Q:
    params = plain_params(params)
    query = Q()
    if params.get("management_company"):
        query &= Q(management_company__name__icontains=params["management_company"])
    if params.get("classification"):
        query &= Q(classification=params["classification"])
    if params.get("subscriber_type"):
        query &= Q(subscriber_type=params["subscriber_type"])
    return query


def snapshot_as_of(as_of: date | None = None, params=None, max_age_days: int | None = None):
    params = plain_params(params)
    as_of = as_of or latest_available_date()
    if as_of is None:
        return FundPerformanceSnapshot.objects.none()
    max_age_days = max_age_days if max_age_days is not None else settings.ASFIM_STALENESS_DAYS
    lower_bound = as_of - timedelta(days=max_age_days)
    base = FundPerformanceSnapshot.objects.filter(date__lte=as_of, date__gte=lower_bound).filter(filtered_funds(params))
    latest_date = (
        base.filter(fund=OuterRef("fund"))
        .order_by("-date")
        .values("date")[:1]
    )
    return (
        base.filter(date=Subquery(latest_date))
        .select_related("fund", "fund__management_company")
        .order_by("fund__management_company__name", "fund__name")
    )


def market_share_payload(as_of: date | None = None, params=None) -> dict[str, object]:
    params = plain_params(params)
    qs = snapshot_as_of(as_of, params)
    company_aum = defaultdict(Decimal)
    for row in qs.order_by().values("fund__management_company__name").annotate(aum=Sum("net_assets")):
        company_aum[row["fund__management_company__name"]] += row["aum"] or Decimal("0")
    structure = market_structure(company_aum)
    return {
        "as_of": (as_of or latest_available_date()).isoformat() if (as_of or latest_available_date()) else None,
        **structure,
    }


def nearest_snapshot_date(as_of: date | None, params=None) -> date | None:
    params = plain_params(params)
    qs = FundPerformanceSnapshot.objects.filter(filtered_funds(params))
    if not qs.exists():
        return None
    if as_of is None:
        return qs.aggregate(value=Max("date"))["value"]
    before = qs.filter(date__lte=as_of).aggregate(value=Max("date"))["value"]
    if before:
        return before
    return qs.order_by("date").values_list("date", flat=True).first()


def aggregate_bucket(qs, field: str, label: str) -> list[dict[str, object]]:
    total = qs.aggregate(value=Sum("net_assets"))["value"] or Decimal("0")
    rows = []
    for row in qs.order_by().values(field).annotate(aum=Sum("net_assets")).order_by("-aum"):
        name = row[field] or "Non renseigné"
        aum = row["aum"] or Decimal("0")
        rows.append(
            {
                label: name,
                "aum": float(aum),
                "market_share": float(aum / total * Decimal("100")) if total > 0 else None,
            }
        )
    return rows


def sampled_snapshot_dates(start: date, end: date, params, max_points: int = 160) -> list[date]:
    dates = list(
        FundPerformanceSnapshot.objects.filter(filtered_funds(params), date__gte=start, date__lte=end)
        .order_by("date")
        .values_list("date", flat=True)
        .distinct()
    )
    if len(dates) <= max_points:
        return dates
    step = (len(dates) - 1) / (max_points - 1)
    indexes = sorted({round(index * step) for index in range(max_points)})
    return [dates[index] for index in indexes]


def market_aum_timeseries(start: date, end: date, params) -> list[dict[str, object]]:
    points = []
    for point_date in sampled_snapshot_dates(start, end, params):
        total = snapshot_as_of(point_date, params).aggregate(value=Sum("net_assets"))["value"] or Decimal("0")
        points.append({"date": point_date, "total_aum": float(total)})
    return points


def market_overview_payload(params) -> dict[str, object]:
    params = plain_params(params)
    end = parse_date_param(params.get("end") or params.get("date"), latest_available_date())
    start = parse_date_param(params.get("start"))
    if end is None:
        return {"as_of": None, "total_aum": 0, "aum_change": None, "time_series": []}
    if start is None:
        start = end - timedelta(days=365)

    end_qs = snapshot_as_of(end, params)
    start_qs = snapshot_as_of(start, params)
    end_total = end_qs.aggregate(value=Sum("net_assets"))["value"] or Decimal("0")
    start_total = start_qs.aggregate(value=Sum("net_assets"))["value"] or Decimal("0")
    company_aum = defaultdict(Decimal)
    for row in end_qs.order_by().values("fund__management_company__name").annotate(aum=Sum("net_assets")):
        company_aum[row["fund__management_company__name"]] += row["aum"] or Decimal("0")
    structure = market_structure(company_aum)
    return {
        "as_of": end.isoformat(),
        "start": start.isoformat(),
        "total_aum": float(end_total),
        "aum_change": float(end_total - start_total) if start_total else None,
        "aum_change_pct": float((end_total - start_total) / start_total * Decimal("100")) if start_total else None,
        "fund_count": end_qs.values("fund_id").distinct().count(),
        "management_company_count": end_qs.values("fund__management_company_id").distinct().count(),
        "hhi": structure["hhi"],
        "top3": structure["top3"],
        "top5": structure["top5"],
        "leader": structure["leader"],
        "leader_share": structure["leader_share"],
        "by_company": structure["shares"],
        "by_legal_nature": aggregate_bucket(end_qs, "fund__legal_nature", "legal_nature"),
        "by_classification": aggregate_bucket(end_qs, "fund__classification", "classification"),
        "by_subscriber_type": aggregate_bucket(end_qs, "fund__subscriber_type", "subscriber_type"),
        "time_series": market_aum_timeseries(start, end, params),
    }


def sr_effect_payload(params) -> list[dict[str, object]]:
    params = plain_params(params)
    start, end = sr_date_window(params)
    qs = sr_base_queryset(params, start, end)
    observations = []
    meta = {}
    results = []
    latest_per_fund = params.get("latest") in {"1", "true", "True", "yes"}
    for isin, fund_name, company, classification, snap_date, net_assets, nav in qs.iterator(chunk_size=5000):
        if net_assets is None or nav is None:
            continue
        observations.append(Observation(snap_date, isin, net_assets, nav))
        meta[isin] = {"fund_name": fund_name, "management_company": company, "classification": classification}
    max_gap_days = int(params["max_gap_days"]) if params.get("max_gap_days") else None
    latest_results = {}
    for result in compute_sr_effect(observations, max_gap_days=max_gap_days):
        info = meta[result.isin]
        payload = {
            "isin": result.isin,
            "date": result.date_t,
            "previous_date": result.date_t1,
            "net_assets": result.net_assets_t,
            "previous_net_assets": result.net_assets_t1,
            "nav": result.nav_t,
            "previous_nav": result.nav_t1,
            "delta_net_assets": result.delta_net_assets,
            "performance_effect": result.performance_effect,
            "sr_effect": result.sr_effect,
            "days": result.days,
            "sr_pct": result.sr_pct,
            **info,
        }
        if latest_per_fund:
            latest_results[result.isin] = payload
        else:
            results.append(payload)
    if latest_per_fund:
        return sorted(latest_results.values(), key=lambda row: abs(row["sr_effect"]), reverse=True)
    max_rows = int(params.get("limit", "5000"))
    if len(results) > max_rows:
        results = sorted(results, key=lambda row: (row["date"], abs(row["sr_effect"])), reverse=True)[:max_rows]
        results.sort(key=lambda row: (row["isin"], row["date"]))
    return results


def category_ranking_payload(params) -> dict[str, object]:
    params = plain_params(params)
    limit = int(params.get("limit", "10"))
    metric = params.get("metric", "sr_effect")
    if metric not in {"sr_effect", "performance_effect", "perf_1y"}:
        metric = "sr_effect"
    sr_params = dict(params)
    sr_params["latest"] = "1"
    sr_params["limit"] = "10000"
    sr_rows = sr_effect_payload(sr_params)
    if params.get("classification"):
        sr_rows = [row for row in sr_rows if row["classification"] == params["classification"]]
    perf_by_isin = {}
    end = parse_date_param(params.get("end") or params.get("date"), latest_available_date())
    for snap in snapshot_as_of(end, params):
        perf_by_isin[snap.fund.isin] = float(snap.perf_1y) if snap.perf_1y is not None else None

    grouped = defaultdict(list)
    for row in sr_rows:
        item = {
            "isin": row["isin"],
            "fund_name": row["fund_name"],
            "management_company": row["management_company"],
            "classification": row["classification"] or "Non renseigné",
            "sr_effect": float(row["sr_effect"]),
            "performance_effect": float(row["performance_effect"]),
            "perf_1y": perf_by_isin.get(row["isin"]),
        }
        grouped[item["classification"]].append(item)

    def finalize(rows: list[dict[str, object]]) -> dict[str, object]:
        scores = percentile_scores([row.get(metric) for row in rows])
        for idx, row in enumerate(rows):
            row["percentile"] = scores[idx]
        rows.sort(key=lambda row: (row.get(metric) is None, -(row.get(metric) or 0)))
        for idx, row in enumerate(rows, start=1):
            row["rank"] = idx
        values = sorted(float(row[metric]) for row in rows if row.get(metric) is not None)
        median = None
        if values:
            middle = len(values) // 2
            median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
        return {
            "average": sum(values) / len(values) if values else None,
            "median": median,
            "rows": rows[:limit],
        }

    if params.get("classification"):
        return {"metric": metric, "classification": params["classification"], **finalize(grouped.get(params["classification"], []))}
    return {"metric": metric, "categories": {key: finalize(rows) for key, rows in sorted(grouped.items())}}


def nav_series_payload(params) -> dict[str, object]:
    params = plain_params(params)
    isins = [item.strip() for item in params.get("isins", "").split(",") if item.strip()]
    if len(isins) > 10:
        raise ValueError("10 ISIN maximum")
    start, end = sr_date_window(params)
    qs = FundPerformanceSnapshot.objects.select_related("fund").filter(fund__isin__in=isins)
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    base100 = params.get("base100", "true").lower() in {"1", "true", "yes"}
    grouped = defaultdict(list)
    names = {}
    for snap in qs.order_by("fund__isin", "date"):
        if snap.nav is None or snap.nav <= 0:
            continue
        names[snap.fund.isin] = snap.fund.name
        grouped[snap.fund.isin].append({"date": snap.date, "nav": float(snap.nav)})
    series = []
    for isin in isins:
        points = grouped.get(isin, [])
        if base100 and points:
            base = points[0]["nav"]
            points = [{"date": item["date"], "nav": item["nav"], "value": item["nav"] / base * 100} for item in points]
        else:
            points = [{"date": item["date"], "nav": item["nav"], "value": item["nav"]} for item in points]
        series.append({"isin": isin, "fund_name": names.get(isin, isin), "points": points})
    return {"base100": base100, "series": series}


def sr_effect_timeseries_payload(params) -> dict[str, object]:
    params = plain_params(params)
    isins = [item.strip() for item in params.get("isins", "").split(",") if item.strip()]
    if len(isins) > 10:
        raise ValueError("10 ISIN maximum")
    if not isins and not params.get("classification"):
        return {"series": []}
    query_params = dict(params)
    query_params.pop("latest", None)
    rows = sr_effect_payload(query_params)
    if isins:
        rows = [row for row in rows if row["isin"] in isins]
    points = [
        {
            "date": row["date"],
            "isin": row["isin"],
            "fund_name": row["fund_name"],
            "sr_effect": float(row["sr_effect"]),
            "performance_effect": float(row["performance_effect"]),
            "sr_pct": float(row["sr_pct"]),
        }
        for row in rows
    ]
    return {"series": points}


def sr_date_window(params: dict[str, str]) -> tuple[date | None, date | None]:
    end = parse_date_param(params.get("end") or params.get("date"))
    start = parse_date_param(params.get("start"))
    if end is None and start is None:
        end = latest_available_date()
    if end is not None and start is None:
        start = end - timedelta(days=365)
    return start, end


def sr_base_queryset(params: dict[str, str], start: date | None, end: date | None):
    qs = FundPerformanceSnapshot.objects.filter(filtered_funds(params))
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    if params.get("isin"):
        qs = qs.filter(fund__isin=params["isin"])
    return (
        qs.order_by("fund__isin", "date")
        .values_list(
            "fund__isin",
            "fund__name",
            "fund__management_company__name",
            "fund__classification",
            "date",
            "net_assets",
            "nav",
        )
    )


def company_sr_totals(params: dict[str, str], start: date, end: date) -> dict[str, Decimal]:
    rows = sr_effect_payload({**params, "start": start.isoformat(), "end": end.isoformat(), "limit": "100000"})
    totals = defaultdict(Decimal)
    for row in rows:
        totals[row["management_company"]] += row["sr_effect"]
    return totals


def fund_risk_metrics(fund: Fund, years: int = 3) -> dict[str, object]:
    latest = fund.snapshots.aggregate(value=Max("date"))["value"]
    qs = fund.snapshots.all()
    if latest:
        qs = qs.filter(date__gte=latest - timedelta(days=365 * years))
    metric = compute_risk_metrics(
        fund.isin,
        list(qs.order_by("date").values_list("date", "nav")),
        risk_free_rate=settings.ASFIM_RISK_FREE_RATE,
    )
    return metric.__dict__


def competitive_payload(params) -> dict[str, object]:
    params = plain_params(params)
    as_of = parse_date_param(params.get("date"), latest_available_date())
    start = parse_date_param(params.get("start"))
    if as_of is None:
        return {"start_date_requested": None, "start_date_used": None, "results": []}
    if start is None:
        start = as_of - timedelta(days=365)

    end_snapshot = list(snapshot_as_of(as_of, params))
    start_snapshot = list(snapshot_as_of(start, params))
    start_date_requested = start
    start_date_used = start
    if not start_snapshot:
        fallback = nearest_snapshot_date(start, params)
        if fallback:
            start_date_used = fallback
            start_snapshot = list(snapshot_as_of(fallback, params, max_age_days=36500))
    end_total = sum((row.net_assets or Decimal("0")) for row in end_snapshot)
    start_total = sum((row.net_assets or Decimal("0")) for row in start_snapshot)

    end_by_company = defaultdict(lambda: {"aum": Decimal("0"), "funds": set(), "fees": Decimal("0"), "perf": []})
    for row in end_snapshot:
        name = row.fund.management_company.name
        aum = row.net_assets or Decimal("0")
        end_by_company[name]["aum"] += aum
        end_by_company[name]["funds"].add(row.fund_id)
        if row.fund.management_fee is not None:
            end_by_company[name]["fees"] += aum * row.fund.management_fee
        if row.perf_1y is not None:
            end_by_company[name]["perf"].append(float(row.perf_1y))

    start_shares = defaultdict(float)
    for row in start_snapshot:
        if start_total > 0 and row.net_assets:
            start_shares[row.fund.management_company.name] += float(row.net_assets / start_total * Decimal("100"))

    sr_params = {key: value for key, value in params.items() if key not in {"date", "start", "end", "scenario"}}
    sr_by_company = company_sr_totals(sr_params, start_date_used, as_of)

    rows = []
    for company, values in end_by_company.items():
        market_share = float(values["aum"] / end_total * Decimal("100")) if end_total > 0 else None
        sr = sr_by_company[company]
        rows.append(
            {
                "company": company,
                "aum": float(values["aum"]),
                "fund_count": len(values["funds"]),
                "market_share": market_share,
                "share_gain": market_share - start_shares[company] if market_share is not None else None,
                "sr_effect": float(sr),
                "collection_rate": float(sr / values["aum"] * Decimal("100")) if values["aum"] > 0 else None,
                "performance": sum(values["perf"]) / len(values["perf"]) if values["perf"] else None,
                "estimated_revenue": float(values["fees"]),
            }
        )
    return {
        "start_date_requested": start_date_requested.isoformat() if start_date_requested else None,
        "start_date_used": start_date_used.isoformat() if start_date_used else None,
        "results": competitive_scores(rows, params.get("scenario", "balanced")),
    }


def data_quality_payload(as_of: date | None = None) -> dict[str, object]:
    as_of = as_of or latest_available_date()
    invalid = FundPerformanceSnapshot.objects.filter(Q(net_assets__lte=0) | Q(nav__lte=0)).count()
    latest_by_fund = Fund.objects.annotate(latest_snapshot=Max("snapshots__date")).select_related("management_company")
    buckets = defaultdict(int)
    company = defaultdict(lambda: defaultdict(int))
    for fund in latest_by_fund:
        bucket = stale_bucket(as_of, fund.latest_snapshot) if as_of else "missing"
        buckets[bucket] += 1
        company[fund.management_company.name][bucket] += 1
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "invalid_rows": invalid,
        "staleness_buckets": dict(buckets),
        "companies": [{"company": key, **dict(value)} for key, value in sorted(company.items())],
    }
