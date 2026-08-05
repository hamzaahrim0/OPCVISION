# Generated manually for the ASFIM analytics scaffold.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ManagementCompany",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
            ],
            options={"ordering": ["name"], "verbose_name_plural": "management companies"},
        ),
        migrations.CreateModel(
            name="Fund",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("isin", models.CharField(max_length=32, unique=True)),
                ("maroclear_code", models.CharField(blank=True, max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("legal_nature", models.CharField(blank=True, max_length=128)),
                ("classification", models.CharField(blank=True, max_length=128)),
                ("sensitivity", models.CharField(blank=True, max_length=128)),
                ("benchmark_index", models.CharField(blank=True, max_length=255)),
                ("nav_periodicity", models.CharField(blank=True, max_length=64)),
                ("subscriber_type", models.CharField(blank=True, max_length=128)),
                ("result_allocation", models.CharField(blank=True, max_length=128)),
                ("subscription_fee", models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ("redemption_fee", models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ("management_fee", models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ("depositary", models.CharField(blank=True, max_length=255)),
                ("placement_network", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("management_company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="funds", to="funds.managementcompany")),
            ],
            options={"ordering": ["name", "isin"]},
        ),
        migrations.CreateModel(
            name="FundPerformanceSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("periodicity", models.CharField(max_length=64)),
                ("net_assets", models.DecimalField(blank=True, decimal_places=6, max_digits=24, null=True)),
                ("nav", models.DecimalField(blank=True, decimal_places=8, max_digits=24, null=True)),
                ("perf_ytd", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_1d", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_1w", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_1m", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_3m", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_6m", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_1y", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_2y", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_3y", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("perf_5y", models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("fund", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="snapshots", to="funds.fund")),
            ],
            options={"ordering": ["-date", "fund__isin"]},
        ),
        migrations.AddIndex(model_name="fund", index=models.Index(fields=["classification"], name="funds_fund_classif_7a5a13_idx")),
        migrations.AddIndex(model_name="fund", index=models.Index(fields=["subscriber_type"], name="funds_fund_subscri_9e017d_idx")),
        migrations.AddIndex(model_name="fund", index=models.Index(fields=["management_company"], name="funds_fund_managem_685c1d_idx")),
        migrations.AddIndex(model_name="fundperformancesnapshot", index=models.Index(fields=["date", "periodicity"], name="funds_fundp_date_5aca53_idx")),
        migrations.AddIndex(model_name="fundperformancesnapshot", index=models.Index(fields=["fund", "date"], name="funds_fundp_fund_id_ab5691_idx")),
        migrations.AddConstraint(
            model_name="fundperformancesnapshot",
            constraint=models.UniqueConstraint(fields=("fund", "date", "periodicity"), name="unique_fund_date_periodicity"),
        ),
    ]
