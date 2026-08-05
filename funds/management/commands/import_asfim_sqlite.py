from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from funds.models import Fund, FundPerformanceSnapshot, ManagementCompany


TEXT_FIELDS = {
    "code_maroclear": "maroclear_code",
    "nom_opcvm": "name",
    "nature_juridique": "legal_nature",
    "classification": "classification",
    "sensibilite": "sensitivity",
    "indice_benchmark": "benchmark_index",
    "periodicite_vl": "nav_periodicity",
    "souscripteurs": "subscriber_type",
    "affectation_resultats": "result_allocation",
    "depositaire": "depositary",
    "reseau_placeur": "placement_network",
}

DECIMAL_FUND_FIELDS = {
    "commission_souscription": "subscription_fee",
    "commission_rachat": "redemption_fee",
    "frais_gestion": "management_fee",
}

DECIMAL_SNAPSHOT_FIELDS = {
    "actif_net": "net_assets",
    "vl": "nav",
    "perf_ytd": "perf_ytd",
    "perf_1j": "perf_1d",
    "perf_1sem": "perf_1w",
    "perf_1m": "perf_1m",
    "perf_3m": "perf_3m",
    "perf_6m": "perf_6m",
    "perf_1an": "perf_1y",
    "perf_2ans": "perf_2y",
    "perf_3ans": "perf_3y",
    "perf_5ans": "perf_5y",
}


def clean_text(value) -> str:
    return str(value).strip() if value is not None else ""


def decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = "Import the legacy ASFIM SQLite table opcvm_performances into the normalized schema."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="asfim.db", help="Path to legacy asfim.db")
        parser.add_argument("--truncate", action="store_true", help="Delete current funds and snapshots before import")
        parser.add_argument("--batch-size", type=int, default=5000)

    def handle(self, *args, **options):
        source = Path(options["source"]).expanduser().resolve()
        if not source.exists():
            raise CommandError(f"SQLite source not found: {source}")

        if options["truncate"]:
            self.stdout.write("Truncating existing imported data...")
            FundPerformanceSnapshot.objects.all().delete()
            Fund.objects.all().delete()
            ManagementCompany.objects.all().delete()

        conn = sqlite3.connect(source)
        conn.row_factory = sqlite3.Row
        count = conn.execute("select count(*) from opcvm_performances").fetchone()[0]
        self.stdout.write(f"Importing {count:,} rows from {source}")

        created_snapshots = 0
        seen_funds: dict[str, Fund] = {}
        seen_companies: dict[str, ManagementCompany] = {}

        self.stdout.write("Preparing fund registry...")
        fund_rows = conn.execute(
            """
            select p.*
            from opcvm_performances p
            join (
                select code_isin, max(date) as max_date
                from opcvm_performances
                where code_isin is not null and code_isin != ''
                group by code_isin
            ) latest
              on latest.code_isin = p.code_isin and latest.max_date = p.date
            group by p.code_isin
            """
        ).fetchall()
        with transaction.atomic():
            for row in fund_rows:
                isin = clean_text(row["code_isin"])
                company_name = clean_text(row["societe_gestion"]) or "Unknown"
                company = seen_companies.get(company_name)
                if company is None:
                    company, _ = ManagementCompany.objects.get_or_create(name=company_name)
                    seen_companies[company_name] = company
                fund_defaults = {target: clean_text(row[source_name]) for source_name, target in TEXT_FIELDS.items()}
                fund_defaults["management_company"] = company
                for source_name, target in DECIMAL_FUND_FIELDS.items():
                    fund_defaults[target] = decimal_or_none(row[source_name])
                fund, _ = Fund.objects.update_or_create(isin=isin, defaults=fund_defaults)
                seen_funds[isin] = fund
        self.stdout.write(f"Prepared {len(seen_funds):,} funds.")

        cursor = conn.execute("select * from opcvm_performances order by date, code_isin")
        rows = cursor.fetchmany(options["batch_size"])
        while rows:
            with transaction.atomic():
                snapshot_objects = []
                for row in rows:
                    isin = clean_text(row["code_isin"])
                    if not isin:
                        continue
                    fund = seen_funds.get(isin)
                    if fund is None:
                        continue

                    snapshot_date = date.fromisoformat(row["date"])
                    snapshot_payload = {
                        "fund": fund,
                        "date": snapshot_date,
                        "periodicity": clean_text(row["periodicite"]),
                    }
                    for source_name, target in DECIMAL_SNAPSHOT_FIELDS.items():
                        snapshot_payload[target] = decimal_or_none(row[source_name])
                    snapshot_objects.append(FundPerformanceSnapshot(**snapshot_payload))

                FundPerformanceSnapshot.objects.bulk_create(
                    snapshot_objects,
                    batch_size=options["batch_size"],
                    update_conflicts=True,
                    unique_fields=["fund", "date", "periodicity"],
                    update_fields=list(DECIMAL_SNAPSHOT_FIELDS.values()),
                )
                created_snapshots += len(snapshot_objects)
            self.stdout.write(f"Imported {created_snapshots:,}/{count:,} snapshots", ending="\r")
            rows = cursor.fetchmany(options["batch_size"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Imported {created_snapshots:,} snapshots."))
