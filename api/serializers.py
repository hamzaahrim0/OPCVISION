from rest_framework import serializers

from funds.models import Fund, FundPerformanceSnapshot, ManagementCompany


class ManagementCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagementCompany
        fields = ["id", "name"]


class FundSerializer(serializers.ModelSerializer):
    management_company = serializers.CharField(source="management_company.name")

    class Meta:
        model = Fund
        fields = [
            "id",
            "isin",
            "maroclear_code",
            "name",
            "management_company",
            "legal_nature",
            "classification",
            "sensitivity",
            "benchmark_index",
            "nav_periodicity",
            "subscriber_type",
            "subscription_fee",
            "redemption_fee",
            "management_fee",
        ]


class FundSnapshotSerializer(serializers.ModelSerializer):
    isin = serializers.CharField(source="fund.isin")
    fund_name = serializers.CharField(source="fund.name")
    management_company = serializers.CharField(source="fund.management_company.name")
    classification = serializers.CharField(source="fund.classification")
    subscriber_type = serializers.CharField(source="fund.subscriber_type")

    class Meta:
        model = FundPerformanceSnapshot
        fields = [
            "date",
            "periodicity",
            "isin",
            "fund_name",
            "management_company",
            "classification",
            "subscriber_type",
            "net_assets",
            "nav",
            "perf_ytd",
            "perf_1d",
            "perf_1w",
            "perf_1m",
            "perf_3m",
            "perf_6m",
            "perf_1y",
            "perf_2y",
            "perf_3y",
            "perf_5y",
        ]
