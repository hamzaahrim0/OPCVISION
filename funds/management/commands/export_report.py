from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from analytics.repository import competitive_payload, data_quality_payload, latest_available_date, market_share_payload


class Command(BaseCommand):
    help = "Generate a compact PDF executive report from the shared analytics services."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="reports/asfim_report.pdf")

    def handle(self, *args, **options):
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        as_of = latest_available_date()
        market = market_share_payload(as_of, {})
        quality = data_quality_payload(as_of)
        watchlist = competitive_payload({"date": as_of.isoformat()} if as_of else {})[:10]

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(output), pagesize=A4)
        story = [Paragraph("ASFIM Analytics Report", styles["Title"])]
        story.append(Paragraph(f"As of: {as_of or 'n/a'}", styles["Normal"]))
        story.append(Spacer(1, 16))
        story.append(Paragraph("Market Structure", styles["Heading2"]))
        story.append(Paragraph(f"HHI: {market.get('hhi'):.2f} | Top 3: {market.get('top3'):.2f}% | Leader: {market.get('leader')}", styles["Normal"]))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Competitive Watchlist", styles["Heading2"]))
        rows = [["Company", "Share", "Score", "Priority", "S-R Effect"]]
        for item in watchlist:
            rows.append([
                item["company"],
                f"{item.get('market_share') or 0:.2f}%",
                f"{item.get('score') or 0:.1f}",
                item["priority"],
                f"{item.get('sr_effect') or 0:,.0f}",
            ])
        table = Table(rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 12))
        story.append(Paragraph("Data Quality", styles["Heading2"]))
        story.append(Paragraph(f"Invalid rows: {quality['invalid_rows']} | Staleness: {quality['staleness_buckets']}", styles["Normal"]))
        doc.build(story)
        self.stdout.write(self.style.SUCCESS(f"Report written to {output}"))
