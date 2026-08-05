from __future__ import annotations

from django.db import models


class ManagementCompany(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "management companies"

    def __str__(self) -> str:
        return self.name


class Fund(models.Model):
    isin = models.CharField(max_length=32, unique=True)
    maroclear_code = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=255)
    management_company = models.ForeignKey(
        ManagementCompany,
        related_name="funds",
        on_delete=models.PROTECT,
    )
    legal_nature = models.CharField(max_length=128, blank=True)
    classification = models.CharField(max_length=128, blank=True)
    sensitivity = models.CharField(max_length=128, blank=True)
    benchmark_index = models.CharField(max_length=255, blank=True)
    nav_periodicity = models.CharField(max_length=64, blank=True)
    subscriber_type = models.CharField(max_length=128, blank=True)
    result_allocation = models.CharField(max_length=128, blank=True)
    subscription_fee = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    redemption_fee = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    management_fee = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    depositary = models.CharField(max_length=255, blank=True)
    placement_network = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "isin"]
        indexes = [
            models.Index(fields=["classification"]),
            models.Index(fields=["subscriber_type"]),
            models.Index(fields=["management_company"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.isin})"


class FundPerformanceSnapshot(models.Model):
    fund = models.ForeignKey(Fund, related_name="snapshots", on_delete=models.CASCADE)
    date = models.DateField()
    periodicity = models.CharField(max_length=64)
    net_assets = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    nav = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    perf_ytd = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_1d = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_1w = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_1m = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_3m = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_6m = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_1y = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_2y = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_3y = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    perf_5y = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "fund__isin"]
        constraints = [
            models.UniqueConstraint(
                fields=["fund", "date", "periodicity"],
                name="unique_fund_date_periodicity",
            )
        ]
        indexes = [
            models.Index(fields=["date", "periodicity"]),
            models.Index(fields=["fund", "date"]),
        ]

    def __str__(self) -> str:
        return f"{self.fund_id} {self.date} {self.periodicity}"
