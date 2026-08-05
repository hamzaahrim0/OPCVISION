from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="api-health"),
    path("dimensions/", views.dimensions, name="api-dimensions"),
    path("funds/", views.FundListView.as_view(), name="api-funds"),
    path("funds/<str:isin>/", views.FundDetailView.as_view(), name="api-fund-detail"),
    path("funds/<str:isin>/history/", views.fund_history, name="api-fund-history"),
    path("snapshot/", views.snapshot, name="api-snapshot"),
    path("market-share/", views.market_share, name="api-market-share"),
    path("market-overview/", views.market_overview, name="api-market-overview"),
    path("sr-effect/", views.sr_effect, name="api-sr-effect"),
    path("category-ranking/", views.category_ranking, name="api-category-ranking"),
    path("nav-series/", views.nav_series, name="api-nav-series"),
    path("sr-effect-timeseries/", views.sr_effect_timeseries, name="api-sr-effect-timeseries"),
    path("competitive/", views.competitive, name="api-competitive"),
    path("data-quality/", views.data_quality, name="api-data-quality"),
]
