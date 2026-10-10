"use client";

import {
  LineChart,
  Receipt,
  Scale,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Activity,
  ArrowRight,
} from "lucide-react";

export default function BacktestsPage() {
  const experiments = [
    {
      id: "EXP-ENSEMBLE-VOTER-2026",
      strategy: "Multi-Strategy Ensemble Alpha Voter",
      universe: "NIFTY 50 Liquid Equities",
      trades: 64,
      grossSharpe: "1.92",
      netSharpe: "1.54",
      dsr: "0.89 (Robust)",
      grossReturn: "+18.4%",
      taxesSlippage: "-3.6%",
      netReturn: "+14.8%",
      maxDD: "-3.8%",
      avgTradeNet: "₹248.50",
      status: "PRODUCTION_CANDIDATE",
    },
    {
      id: "EXP-VWAP-REV-02",
      strategy: "VWAP Mean Reversion (15m)",
      universe: "High-Beta Large Caps (SBIN, RELIANCE)",
      trades: 88,
      grossSharpe: "1.65",
      netSharpe: "1.21",
      dsr: "0.74 (Acceptable)",
      grossReturn: "+15.1%",
      taxesSlippage: "-4.2%",
      netReturn: "+10.9%",
      maxDD: "-5.2%",
      avgTradeNet: "₹182.10",
      status: "PRODUCTION_CANDIDATE",
    },
    {
      id: "EXP-ORB-MOMENTUM-01",
      strategy: "Opening Range Breakout (5m)",
      universe: "NIFTY 50 Top 10",
      trades: 142,
      grossSharpe: "1.45",
      netSharpe: "0.82",
      dsr: "0.41 (Overfitting Warning)",
      grossReturn: "+19.2%",
      taxesSlippage: "-11.8%",
      netReturn: "+7.4%",
      maxDD: "-9.4%",
      avgTradeNet: "₹45.20",
      status: "HIGH_FRICTION_RISK",
    },
  ];

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Title & Philosophy Banner */}
      <div className="p-5 rounded-lg bg-surface border border-surface-border flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono font-bold text-sky-400 bg-sky-500/10 px-2 py-0.5 rounded border border-sky-500/20">
              REALISTIC FRICTION AUDITOR
            </span>
            <span className="text-xs text-slate-400 font-mono">Deflated Sharpe &amp; Tax Drag</span>
          </div>
          <h2 className="text-xl md:text-2xl font-bold text-white mt-1">Backtesting Engine &amp; Net Returns</h2>
          <p className="text-xs text-slate-400 mt-1 max-w-3xl leading-relaxed">
            &ldquo;A backtest with zero transaction costs is fiction. Notice experiment #3 (ORB 5m): high gross return (+19.2%) was decimated by -11.8% in STT and turnover costs due to overtrading. In Indian markets, trade frequency is the enemy of net CAGR.&rdquo;
          </p>
        </div>

        <div className="flex items-center space-x-2 shrink-0 text-xs font-mono bg-black/40 px-3 py-2 rounded border border-surface-border">
          <Receipt className="w-4 h-4 text-amber-400" />
          <span className="text-slate-300">NSE Intraday &amp; STT Deducted</span>
        </div>
      </div>

      {/* 3 Core Modeling Guards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <div className="text-xs text-slate-400 font-mono">SEBI TAX ATTRIBUTION</div>
          <div className="text-sm font-semibold text-white mt-1">Realistic Statutory Slippage</div>
          <div className="text-[11px] text-slate-400 mt-1.5 leading-relaxed">
            0.025% STT on MIS, 18% GST on brokerage, stamp duty, and ₹10/Cr SEBI fee automatically debited on every backtested fill.
          </div>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <div className="text-xs text-slate-400 font-mono">DEFLATED SHARPE (DSR)</div>
          <div className="text-sm font-semibold text-white mt-1">Multiple Testing Correction</div>
          <div className="text-[11px] text-slate-400 mt-1.5 leading-relaxed">
            Bailey &amp; López de Prado DSR framework: Penalizes trial count to prevent discovering fake alpha through curve-fitting.
          </div>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <div className="text-xs text-slate-400 font-mono">EXECUTION TIME SENSITIVITY</div>
          <div className="text-sm font-semibold text-white mt-1">1-Bar Execution Lag</div>
          <div className="text-[11px] text-slate-400 mt-1.5 leading-relaxed">
            Signal generated at Bar[T] close is executed strictly at Bar[T+1] Open + tick slippage. Zero look-ahead bias guaranteed.
          </div>
        </div>
      </div>

      {/* Backtested Strategies Comparison */}
      <div className="rounded-lg bg-surface border border-surface-border overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-border flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Backtest Experiment Journal (Gross vs Net Reality)</h3>
          <span className="text-xs font-mono text-emerald-400">100% REPRODUCIBLE (GIT TAGGED)</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-black/40 text-slate-400 border-b border-surface-border">
              <tr>
                <th className="p-3">Experiment ID</th>
                <th className="p-3">Strategy</th>
                <th className="p-3">Trades</th>
                <th className="p-3">Gross Sharpe</th>
                <th className="p-3">Net Sharpe</th>
                <th className="p-3">DSR</th>
                <th className="p-3">Gross Return</th>
                <th className="p-3">Taxes &amp; Slip</th>
                <th className="p-3">Net In-Pocket</th>
                <th className="p-3">Max DD</th>
                <th className="p-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border text-slate-300">
              {experiments.map((exp) => (
                <tr key={exp.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="p-3 font-bold text-accent">{exp.id}</td>
                  <td className="p-3 font-sans font-medium text-white">{exp.strategy}</td>
                  <td className="p-3">{exp.trades}</td>
                  <td className="p-3 text-slate-400">{exp.grossSharpe}</td>
                  <td className="p-3 font-bold text-sky-400">{exp.netSharpe}</td>
                  <td className="p-3 text-slate-300">{exp.dsr}</td>
                  <td className="p-3 text-slate-400">{exp.grossReturn}</td>
                  <td className="p-3 text-rose-400">{exp.taxesSlippage}</td>
                  <td className="p-3 font-bold text-emerald-400">{exp.netReturn}</td>
                  <td className="p-3 text-rose-300">{exp.maxDD}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      exp.status === "PRODUCTION_CANDIDATE"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                    }`}>
                      {exp.status.replace("_", " ")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
