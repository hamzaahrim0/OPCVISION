from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase

from analytics.repository import category_ranking_payload, market_overview_payload, nav_series_payload
from funds.models import Fund, FundPerformanceSnapshot, ManagementCompany


class RepositoryPayloadTests(TestCase):
    def setUp(self):
        alpha = ManagementCompany.objects.create(name="Alpha AM")
        beta = ManagementCompany.objects.create(name="Beta AM")
        self.fund_a = Fund.objects.create(
            isin="MA0001",
            name="Alpha Actions",
            management_company=alpha,
            legal_nature="FCP",
            classification="ACTIONS",
            subscriber_type="Grand public",
        )
        self.fund_b = Fund.objects.create(
            isin="MA0002",
            name="Beta Actions",
            management_company=beta,
            legal_nature="SICAV",
            classification="ACTIONS",
            subscriber_type="Grand public",
        )
        self.fund_c = Fund.objects.create(
            isin="MA0003",
            name="Alpha Monetaire",
            management_company=alpha,
            legal_nature="FCP",
            classification="MONETAIRE",
            subscriber_type="Institutionnels",
        )
        self._snapshot(self.fund_a, date(2026, 1, 1), "1000", "100", "4")
        self._snapshot(self.fund_a, date(2026, 1, 8), "1120", "105", "5")
        self._snapshot(self.fund_b, date(2026, 1, 1), "900", "100", "2")
        self._snapshot(self.fund_b, date(2026, 1, 8), "930", "101", "3")
        self._snapshot(self.fund_c, date(2026, 1, 8), "500", "100", "1")

    def _snapshot(self, fund, snap_date, net_assets, nav, perf_1y):
        FundPerformanceSnapshot.objects.create(
            fund=fund,
            date=snap_date,
            periodicity="quotidienne",
            net_assets=Decimal(net_assets),
            nav=Decimal(nav),
            perf_1y=Decimal(perf_1y),
        )

    def test_market_overview_groups_aum_by_legal_nature(self):
        payload = market_overview_payload({"start": "2026-01-01", "end": "2026-01-08"})

        by_nature = {row["legal_nature"]: row["aum"] for row in payload["by_legal_nature"]}

        self.assertEqual(by_nature["FCP"], 1620.0)
        self.assertEqual(by_nature["SICAV"], 930.0)
        self.assertEqual(payload["total_aum"], 2550.0)

    def test_market_timeseries_uses_snapshot_totals_not_raw_publication_day_sum(self):
        self._snapshot(self.fund_a, date(2026, 1, 4), "1130", "106", "5")

        payload = market_overview_payload({"start": "2026-01-01", "end": "2026-01-08"})
        by_date = {row["date"]: row["total_aum"] for row in payload["time_series"]}

        self.assertEqual(by_date[date(2026, 1, 4)], 2030.0)

    def test_category_ranking_is_sorted_and_has_percentiles(self):
        payload = category_ranking_payload(
            {"classification": "ACTIONS", "metric": "sr_effect", "start": "2026-01-01", "end": "2026-01-08", "limit": "10"}
        )

        rows = payload["rows"]

        self.assertEqual([row["isin"] for row in rows], ["MA0001", "MA0002"])
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["percentile"], 100.0)
        self.assertEqual(rows[1]["percentile"], 0.0)
        self.assertEqual(payload["median"], 45.5)

    def test_nav_series_normalizes_base_100(self):
        payload = nav_series_payload({"isins": "MA0001,MA0002", "start": "2026-01-01", "end": "2026-01-08", "base100": "true"})

        series = {row["isin"]: row["points"] for row in payload["series"]}

        self.assertEqual(series["MA0001"][0]["value"], 100.0)
        self.assertEqual(series["MA0001"][1]["value"], 105.0)
        self.assertEqual(series["MA0002"][1]["value"], 101.0)
