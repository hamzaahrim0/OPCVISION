from __future__ import annotations

from django.db.models import Max, Min, Q
from django.http import HttpResponse
from django.core.cache import cache
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from analytics.repository import (
    category_ranking_payload,
    competitive_payload,
    data_quality_payload,
    fund_risk_metrics,
    latest_available_date,
    market_overview_payload,
    market_share_payload,
    nav_series_payload,
    parse_date_param,
    snapshot_as_of,
    sr_effect_payload,
    sr_effect_timeseries_payload,
)
from api.serializers import FundSerializer, FundSnapshotSerializer
from funds.models import Fund, FundPerformanceSnapshot


ANALYTICS_CACHE_TTL = 60


def cached_payload(request, namespace: str, builder, ttl: int = ANALYTICS_CACHE_TTL):
    key = f"api:{namespace}:{request.get_full_path()}"
    payload = cache.get(key)
    if payload is None:
        payload = builder()
        cache.set(key, payload, ttl)
    return Response(payload)


class FundListView(generics.ListAPIView):
    serializer_class = FundSerializer

    def get_queryset(self):
        qs = Fund.objects.select_related("management_company").all()
        params = self.request.query_params
        if params.get("management_company"):
            qs = qs.filter(management_company__name__icontains=params["management_company"])
        if params.get("classification"):
            qs = qs.filter(classification=params["classification"])
        if params.get("subscriber_type"):
            qs = qs.filter(subscriber_type=params["subscriber_type"])
        if params.get("search"):
            search_term = params["search"].strip()
            if " - " in search_term:
                isin_part, _, name_part = search_term.partition(" - ")
                qs = qs.filter(Q(isin__icontains=isin_part.strip()) | Q(name__icontains=name_part.strip()))
            else:
                qs = qs.filter(Q(name__icontains=search_term) | Q(isin__icontains=search_term))
        return qs


class FundDetailView(generics.RetrieveAPIView):
    serializer_class = FundSerializer
    lookup_field = "isin"
    queryset = Fund.objects.select_related("management_company").all()

    def retrieve(self, request, *args, **kwargs):
        fund = self.get_object()
        payload = self.get_serializer(fund).data
        latest = fund.snapshots.order_by("-date").first()
        payload["latest_snapshot"] = FundSnapshotSerializer(latest).data if latest else None
        payload["risk_metrics"] = fund_risk_metrics(fund)
        return Response(payload)


@api_view(["GET"])
def fund_history(request, isin: str):
    qs = FundPerformanceSnapshot.objects.select_related("fund", "fund__management_company").filter(fund__isin=isin)
    start = parse_date_param(request.query_params.get("start"))
    end = parse_date_param(request.query_params.get("end"))
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    return Response(FundSnapshotSerializer(qs.order_by("date"), many=True).data)


@api_view(["GET"])
def snapshot(request):
    as_of = parse_date_param(request.query_params.get("date"), latest_available_date())
    def payload():
        qs = snapshot_as_of(as_of, request.query_params)
        if request.query_params.get("limit"):
            try:
                limit = min(int(request.query_params["limit"]), 500)
            except ValueError:
                limit = 120
            qs = qs[:limit]
        return FundSnapshotSerializer(qs, many=True).data

    return cached_payload(request, "snapshot", payload, ttl=30)


@api_view(["GET"])
def market_share(request):
    as_of = parse_date_param(request.query_params.get("date"), latest_available_date())
    return cached_payload(request, "market-share", lambda: market_share_payload(as_of, request.query_params))


@api_view(["GET"])
def market_overview(request):
    return cached_payload(request, "market-overview", lambda: market_overview_payload(request.query_params))


@api_view(["GET"])
def sr_effect(request):
    return cached_payload(request, "sr-effect", lambda: sr_effect_payload(request.query_params), ttl=30)


@api_view(["GET"])
def category_ranking(request):
    return cached_payload(request, "category-ranking", lambda: category_ranking_payload(request.query_params), ttl=30)


@api_view(["GET"])
def nav_series(request):
    try:
        return cached_payload(request, "nav-series", lambda: nav_series_payload(request.query_params), ttl=30)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def sr_effect_timeseries(request):
    try:
        return cached_payload(request, "sr-effect-timeseries", lambda: sr_effect_timeseries_payload(request.query_params), ttl=30)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def competitive(request):
    return cached_payload(request, "competitive", lambda: competitive_payload(request.query_params), ttl=30)


@api_view(["GET"])
def data_quality(request):
    return cached_payload(
        request,
        "data-quality",
        lambda: data_quality_payload(parse_date_param(request.query_params.get("date"), latest_available_date())),
    )


@api_view(["GET"])
def dimensions(request):
    def payload():
        dates = FundPerformanceSnapshot.objects.aggregate(latest=Max("date"), earliest=Min("date"))
        return {
            "latest_date": dates["latest"],
            "earliest_date": dates["earliest"],
            "classifications": list(Fund.objects.exclude(classification="").order_by("classification").values_list("classification", flat=True).distinct()),
            "subscriber_types": list(Fund.objects.exclude(subscriber_type="").order_by("subscriber_type").values_list("subscriber_type", flat=True).distinct()),
            "management_companies": list(Fund.objects.order_by("management_company__name").values_list("management_company__name", flat=True).distinct()),
        }

    return cached_payload(request, "dimensions", payload, ttl=300)


def health(_request):
    return HttpResponse("ok", content_type="text/plain")
