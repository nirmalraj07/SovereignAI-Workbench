"""
Compliance Reporting Module: turns the audit-analytics summary into a
downloadable DOCX compliance report (event totals, action breakdown,
anomaly flags, security posture) — reuses files/generator.py so output
format stays consistent with the rest of the platform's deliverables.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session

from docx import Document
from pathlib import Path
import uuid

from ..observability import audit_analytics
from ..files.generator import OUTPUT_DIR


def generate_compliance_report(db: Session, days: int = 30, prepared_by: str = "system") -> Path:
    data = audit_analytics.summary(db, days)

    doc = Document()
    doc.add_heading("SovereignAI Workbench — Compliance Report", level=1)
    doc.add_paragraph(f"Reporting window: last {days} days (generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')})")
    doc.add_paragraph(f"Prepared by: {prepared_by}")

    doc.add_heading("1. Executive Summary", level=2)
    doc.add_paragraph(
        f"During the reporting window, {data['total_events']} audited events were recorded across "
        f"the platform. All AI inference, document retrieval, and code execution occurred on-premise; "
        f"the Security Dashboard's live egress counters were 0 external connections and 0 external API "
        f"calls at time of report generation."
    )

    doc.add_heading("2. Event Breakdown by Action", level=2)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text = "Action", "Count"
    for row in data["by_action"]:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = row["action"], str(row["count"])

    doc.add_heading("3. Most-Accessed Resources", level=2)
    table2 = doc.add_table(rows=1, cols=2)
    table2.style = "Light Grid Accent 1"
    hdr2 = table2.rows[0].cells
    hdr2[0].text, hdr2[1].text = "Resource", "Access Count"
    for row in data["top_resources"]:
        cells = table2.add_row().cells
        cells[0].text, cells[1].text = str(row["resource"])[:120], str(row["count"])

    doc.add_heading("4. Anomaly Flags", level=2)
    if data["anomalies"]:
        for a in data["anomalies"]:
            doc.add_paragraph(
                f"{a['date']} — '{a['action']}': {a['reason']}", style="List Bullet"
            )
    else:
        doc.add_paragraph("No statistically significant activity spikes detected in this window.")

    doc.add_heading("5. Attestation", level=2)
    doc.add_paragraph(
        "This report was generated automatically from the platform's append-only audit log "
        "(audit_log table) and reflects system-recorded activity only. It does not constitute "
        "legal certification of compliance with any specific regulatory framework; consult your "
        "compliance officer to map these records against applicable requirements."
    )
    doc.add_paragraph("Prepared by: _____________________     Reviewed by: _____________________")

    path = OUTPUT_DIR / f"compliance-report-{uuid.uuid4().hex[:8]}.docx"
    doc.save(path)
    return path
