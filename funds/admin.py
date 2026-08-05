from django.contrib import admin

from .models import Fund, FundPerformanceSnapshot, ManagementCompany


@admin.register(ManagementCompany)
class ManagementCompanyAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ["isin", "name", "management_company", "classification", "subscriber_type"]
    list_filter = ["classification", "subscriber_type", "management_company"]
    search_fields = ["isin", "name", "management_company__name"]


@admin.register(FundPerformanceSnapshot)
class FundPerformanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ["fund", "date", "periodicity", "net_assets", "nav"]
    list_filter = ["periodicity", "date"]
    search_fields = ["fund__isin", "fund__name"]
