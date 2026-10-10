"""
QUANT-OS Stage 6 - EOD Automated Auditor & Financial Report Generator (eod_report_gen.py)
Automates end-of-day Truth Check: Asset Reconciliation (Zero Variance),
Statutory Friction Breakdown, Net P&L calculation, and PDF/JSON audit report delivery.
"""

import os
import json
import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.scripts.reconciliation import AssetReconciler
from services.backtest_engine.statutory_cost_model import IndianStatutoryCostModel, OrderLeg, ProductType


class EODReportGenerator:
    """Automates post-market close financial audit and report generation."""

    def __init__(self, audit_dir: str = "/home/ubuntu/algolab/audit"):
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def generate_eod_audit_report(
        self,
        gateway: BrokerGateway,
        strategy_id: str = "STRAT_HYBRID_001",
        initial_capital: float = 100000.0,
        trades: Optional[List[Dict[str, Any]]] = None,
        operational_logs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Runs asset reconciliation, computes statutory friction breakdown,
        and generates timestamped JSON and PDF reports.
        """
        timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

        # 1. Run Asset Reconciliation
        reconciler = AssetReconciler(gateway, gateway.paper_exchange)
        recon_report = reconciler.run_reconciliation(strategy_id)

        # 2. Calculate Statutory Costs & P&L
        final_equity = gateway.get_broker_ledger_total_assets(strategy_id)
        gross_pnl = final_equity - initial_capital

        total_brokerage = Decimal("0.0")
        total_stt = Decimal("0.0")
        total_exchange_fee = Decimal("0.0")
        total_sebi_fee = Decimal("0.0")
        total_stamp_duty = Decimal("0.0")
        total_gst = Decimal("0.0")
        total_friction = Decimal("0.0")

        executed_trades = trades or []
        for t in executed_trades:
            price = Decimal(str(t.get("price", 1000.0)))
            qty = int(t.get("qty", 10))
            side_str = str(t.get("side", "BUY")).upper()
            leg = OrderLeg.BUY if side_str == "BUY" else OrderLeg.SELL

            fric = IndianStatutoryCostModel.calculate_order_friction(
                leg=leg,
                price=price,
                quantity=qty,
                product=ProductType.INTRADAY,
                slippage_bps=Decimal("1.0"),
            )
            total_brokerage += fric.brokerage
            total_stt += fric.stt
            total_exchange_fee += fric.exchange_txn_fee
            total_sebi_fee += fric.sebi_turnover_fee
            total_stamp_duty += fric.stamp_duty
            total_gst += fric.gst
            total_friction += fric.total_statutory_and_brokerage

        net_pnl = gross_pnl - float(total_friction)
        net_pnl_pct = (net_pnl / initial_capital) * 100.0 if initial_capital > 0 else 0.0

        audit_data = {
            "report_id": f"EOD_{timestamp_str}",
            "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "strategy_id": strategy_id,
            "financial_summary": {
                "initial_capital": round(initial_capital, 2),
                "final_equity": round(final_equity, 2),
                "gross_pnl": round(gross_pnl, 2),
                "statutory_friction": {
                    "brokerage": float(total_brokerage),
                    "stt": float(total_stt),
                    "exchange_txn_fee": float(total_exchange_fee),
                    "sebi_turnover_fee": float(total_sebi_fee),
                    "stamp_duty": float(total_stamp_duty),
                    "gst": float(total_gst),
                    "total_friction": float(total_friction),
                },
                "net_pnl": round(net_pnl, 2),
                "net_pnl_pct": round(net_pnl_pct, 2),
            },
            "reconciliation_audit": {
                "status": recon_report["status"],
                "variance": recon_report["variance"],
                "broker_ledger_assets": recon_report["broker_ledger"]["total_assets"],
                "exchange_cash_balance": recon_report["paper_exchange"]["cash_balance"],
                "is_zero_variance": recon_report["variance"] == 0.0,
            },
            "operational_health": {
                "total_trades_executed": len(executed_trades),
                "kill_switch_active": gateway.kill_switch_active,
                "simulation_mode": gateway.simulation_mode,
                "logs_sample": operational_logs or ["EOD Audit Completed Successfully"],
            },
            "executed_trades": executed_trades,
        }

        # 3. Save JSON Report
        json_path = self.audit_dir / f"eod_report_{timestamp_str}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(audit_data, f, indent=2)

        # 4. Generate PDF Report
        pdf_path = self.audit_dir / f"eod_report_{timestamp_str}.pdf"
        self._build_pdf_report(pdf_path, audit_data)

        audit_data["json_report_file"] = str(json_path)
        audit_data["pdf_report_file"] = str(pdf_path)
        return audit_data

    def _build_pdf_report(self, pdf_path: Path, data: Dict[str, Any]):
        """Builds a formatted PDF report using ReportLab."""
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0f172a"),
        )
        subtitle_style = ParagraphStyle(
            "SubTitle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#475569"),
            spaceAfter=12,
        )
        section_style = ParagraphStyle(
            "SectionHeader",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=10,
            spaceAfter=6,
        )

        elements = []

        # Title Block
        elements.append(Paragraph("QUANT-OS EOD Financial & Operational Audit Report", title_style))
        elements.append(Paragraph(f"Report ID: {data['report_id']} | Generated: {data['generated_at_utc']}", subtitle_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=15))

        # Financial Summary Table
        fin = data["financial_summary"]
        fric = fin["statutory_friction"]
        fin_data = [
            ["Financial Metric", "Amount (₹)"],
            ["Initial Capital", f"₹{fin['initial_capital']:,.2f}"],
            ["Final Equity", f"₹{fin['final_equity']:,.2f}"],
            ["Gross P&L", f"₹{fin['gross_pnl']:,.2f}"],
            ["Brokerage Charges", f"₹{fric['brokerage']:,.2f}"],
            ["STT (Securities Transaction Tax)", f"₹{fric['stt']:,.2f}"],
            ["Exchange Txn Fees", f"₹{fric['exchange_txn_fee']:,.2f}"],
            ["SEBI Turnover Fees", f"₹{fric['sebi_turnover_fee']:,.2f}"],
            ["Stamp Duty", f"₹{fric['stamp_duty']:,.2f}"],
            ["GST (18% Service Tax)", f"₹{fric['gst']:,.2f}"],
            ["Total Statutory Friction", f"₹{fric['total_friction']:,.2f}"],
            ["NET P&L (Post-Friction)", f"₹{fin['net_pnl']:,.2f} ({fin['net_pnl_pct']:.2f}%)"],
        ]

        fin_table = Table(fin_data, colWidths=[300, 220])
        fin_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
            ("FONTNAME", (0, 0), (1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("BACKGROUND", (0, -1), (1, -1), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, -1), (1, -1), "Helvetica-Bold"),
        ]))

        elements.append(Paragraph("1. Post-Friction P&L Breakdown", section_style))
        elements.append(fin_table)
        elements.append(Spacer(1, 15))

        # Asset Reconciliation Table
        recon = data["reconciliation_audit"]
        recon_data = [
            ["Reconciliation Audit Item", "Audit Status / Value"],
            ["Reconciliation Status", recon["status"]],
            ["Reconciliation Variance (Δ)", f"₹{recon['variance']:.2f}"],
            ["Broker Ledger Total Assets", f"₹{recon['broker_ledger_assets']:,.2f}"],
            ["Exchange Cash Balance", f"₹{recon['exchange_cash_balance']:,.2f}"],
            ["Zero Variance Verified", "PASSED (₹0.00 Variance)" if recon["is_zero_variance"] else "FAILED"],
        ]

        recon_table = Table(recon_data, colWidths=[300, 220])
        recon_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (1, 0), colors.white),
            ("FONTNAME", (0, 0), (1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ]))

        elements.append(Paragraph("2. Asset Reconciliation & Zero Variance Proof", section_style))
        elements.append(recon_table)

        doc.build(elements)
