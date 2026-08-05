from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from analytics.services import Observation, compute_risk_metrics, compute_sr_effect, market_structure


class FinancialFormulaTests(SimpleTestCase):
    def test_sr_effect_decomposes_net_asset_change(self):
        observations = [
            Observation(date(2026, 1, 1), "MA0001", Decimal("1000"), Decimal("100")),
            Observation(date(2026, 1, 8), "MA0001", Decimal("1120"), Decimal("105")),
        ]

        result = compute_sr_effect(observations)[0]

        self.assertEqual(result.delta_net_assets, Decimal("120"))
        self.assertEqual(result.performance_effect, Decimal("50.00"))
        self.assertEqual(result.sr_effect, Decimal("70.00"))
        self.assertEqual(result.sr_pct, Decimal("7.00"))

    def test_sr_effect_excludes_pairs_above_max_gap(self):
        observations = [
            Observation(date(2026, 1, 1), "MA0001", Decimal("1000"), Decimal("100")),
            Observation(date(2026, 2, 10), "MA0001", Decimal("1120"), Decimal("105")),
        ]

        self.assertEqual(compute_sr_effect(observations, max_gap_days=10), [])

    def test_risk_metrics_match_hand_computed_values(self):
        navs = [
            (date(2026, 1, 1) + timedelta(days=i * 3), nav)
            for i, nav in enumerate([100, 101, 100, 102, 103, 102, 104, 106, 105, 107, 108, 107, 109, 111, 110])
        ]

        metrics = compute_risk_metrics("MA0001", navs, risk_free_rate=0.0)

        self.assertEqual(metrics.observations, 15)
        self.assertEqual(metrics.annualization_factor, 252)
        self.assertAlmostEqual(metrics.annualized_return, 1.7417556273518002, places=12)
        self.assertAlmostEqual(metrics.annualized_volatility, 0.20958360658338834, places=12)
        self.assertAlmostEqual(metrics.sharpe, 8.310552794399008, places=12)
        self.assertAlmostEqual(metrics.sortino, 23.299039804945846, places=12)
        self.assertAlmostEqual(metrics.max_drawdown, -0.00990099009900991, places=12)
        self.assertAlmostEqual(metrics.calmar, 175.91731836253166, places=12)

    def test_market_structure_uses_hhi_on_percentage_shares(self):
        result = market_structure({"A": 50, "B": 30, "C": 20})

        self.assertEqual(result["leader"], "A")
        self.assertAlmostEqual(result["hhi"], 3800.0)
        self.assertAlmostEqual(result["top3"], 100.0)
        self.assertAlmostEqual(result["top5"], 100.0)
