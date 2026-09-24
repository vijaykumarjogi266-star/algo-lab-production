"use client";

import Link from "next/link";
import {
  ShieldCheck,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Receipt,
  Scale,
  ArrowRight,
  Activity,
  CheckCircle2,
  Clock,
  Briefcase,
  Layers,
  Power,
} from "lucide-react";

export default function DashboardPage() {
  const nudges = [
    {
      type: "warning",
      title: "Intraday Timing Window (Golden Window)",
      desc: "Strictly deploy new entries between 09:45 AM and 01:00 PM IST. Post-lunch session (13:00–15:15) is reserved strictly for trailing stops and position management.",
      tag: "EXECUTION TIMING",
    },
    {
      type: "info",
      title: "Indian Statutory Friction Awareness",
      desc: "Remember that STT, Stamp Duty, SEBI turnover fees, and 18% GST apply to every fill. A strategy taking 50 trades a day needs a 2x higher gross edge just to break even.",
      tag: "COST AUDITOR",
    },
    {
      type: "success",
      title: "Capital Preservation & Position Sizing",
      desc: "Single-trade risk is hard-capped at ₹300 (0.3% of ₹1L capital). Today's stop-loss on HAL was contained cleanly at -₹1,044 net, well inside our 3% circuit breaker.",
      tag: "RISK PROTOCOL",
    },
  ];

  const tomorrowPlan = [
    { symbol: "SBIN.NS", shares: 13, entry: "₹978.50", sl: "₹957.07", tp: "₹1,032.09", risk: "₹278.59", rr: "1 : 2.50", strategy: "Ensemble Voter (3/3)" },
    { symbol: "RELIANCE.NS", shares: 11, entry: "₹1,219.20", sl: "₹1,194.09", tp: "₹1,281.97", risk: "₹276.21", rr: "1 : 2.50", strategy: "Ensemble Voter (3/3)" },
    { symbol: "TCS.NS", shares: 3, entry: "₹2,087.00", sl: "₹2,010.20", tp: "₹2,279.00", risk: "₹230.40", rr: "1 : 2.50", strategy: "Exploratory Only (N=1)" },
    { symbol: "ITC.NS", shares: 49, entry: "₹268.00", sl: "₹261.99", tp: "₹283.04", risk: "₹294.49", rr: "1 : 2.50", strategy: "Ensemble Voter (3/3)" },
  ];

  return (
    <div className="space-y-8 max-w-6xl">
      {/* Top Banner: Nithin Kamath's Philosophy */}
      <div className="p-5 rounded-lg bg-gradient-to-r from-surface via-slate-900 to-surface border border-surface-border flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
              NITHIN KAMATH&apos;S QUANT REVIEW
            </span>
            <span className="text-xs text-slate-400 font-mono">SEBI Compliant Quantitative OS</span>
          </div>
          <h2 className="text-xl md:text-2xl font-bold text-white mt-2">
            Survival First: Return <span className="text-sky-400">OF</span> Capital &gt; Return <span className="text-emerald-400">ON</span> Capital
          </h2>
          <p className="text-slate-400 text-xs mt-1 max-w-2xl leading-relaxed">
            &ldquo;90% of retail and algorithmic traders fail in Indian markets not due to bad indicators, but due to friction neglect, overtrading, and lack of emotional discipline. Here, every rupee of capital is guarded by hard mathematical barriers.&rdquo;
          </p>
        </div>

        <div className="flex items-center space-x-3 shrink-0">
          <Link
            href="/paper-trading"
            className="px-4 py-2 bg-accent/10 border border-accent/30 hover:bg-accent/20 text-accent rounded text-xs font-mono font-semibold transition-colors flex items-center space-x-1.5"
          >
            <span>Live Positions</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
          <Link
            href="/risk"
            className="px-4 py-2 bg-slate-800 border border-slate-700 hover:border-slate-600 text-slate-200 rounded text-xs font-mono font-semibold transition-colors"
          >
            Kill Switch
          </Link>
        </div>
      </div>

      {/* 4 Core Vital Signs (Kite-Inspired High Density) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-mono font-semibold">CAPITAL PRESERVED</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-white mt-2 font-mono">₹98,955.90</div>
          <p className="text-[11px] text-slate-400 mt-1">
            ₹1,00,000 Base <span className="text-slate-500">• 0.0x Leverage</span>
          </p>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-mono font-semibold">TODAY&apos;S NET P&amp;L</span>
            <TrendingDown className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-xl font-bold text-rose-400 mt-2 font-mono">-₹1,044.10</div>
          <p className="text-[11px] text-slate-400 mt-1">
            -1.04% Capital <span className="text-slate-500">• Contained Stop</span>
          </p>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-mono font-semibold">CIRCUIT BREAKER PROXIMITY</span>
            <Scale className="w-4 h-4 text-sky-400" />
          </div>
          <div className="text-xl font-bold text-sky-400 mt-2 font-mono">34.8% Used</div>
          <p className="text-[11px] text-slate-400 mt-1">
            Max Daily Stop: ₹3,000.00 (3.0%)
          </p>
        </div>

        <div className="p-4 rounded-lg bg-surface border border-surface-border">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-mono font-semibold">TRADER LONGEVITY SCORE</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-emerald-400 mt-2 font-mono">98.2 / 100</div>
          <p className="text-[11px] text-slate-400 mt-1">
            Zero Revenge Trades • Risk Intact
          </p>
        </div>
      </div>

      {/* Zerodha Nudges Panel */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider font-mono">
              Active Zerodha Nudges (Behavioral Guardrails)
            </h3>
          </div>
          <span className="text-[10px] font-mono text-slate-400">
            Preventing the 3 most common retail quant mistakes
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {nudges.map((nudge, idx) => (
            <div key={idx} className="p-4 rounded-lg bg-surface border border-surface-border flex flex-col justify-between space-y-3">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold">
                    {nudge.tag}
                  </span>
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                </div>
                <h4 className="text-xs font-bold text-white mt-2.5">{nudge.title}</h4>
                <p className="text-[11px] text-slate-400 mt-1.5 leading-relaxed">{nudge.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Real-World Indian Friction Auditor (Zerodha Brokerage & Tax Breakdown) */}
      <div className="p-5 rounded-lg bg-surface border border-surface-border">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-surface-border gap-2">
          <div>
            <div className="flex items-center space-x-2">
              <Receipt className="w-4 h-4 text-sky-400" />
              <h3 className="text-sm font-semibold text-white font-mono uppercase tracking-wider">
                Real-World Statutory Friction &amp; Tax Auditor (SEBI / NSE)
              </h3>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              The difference between amateur paper trading and institutional reality: Transparent deduction of all taxes.
            </p>
          </div>
          <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded border border-emerald-500/20 self-start sm:self-auto">
            100% AUDIT TRANSPARENCY
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-4">
          <div className="p-3 rounded bg-black/40 border border-surface-border text-center">
            <span className="text-[10px] font-mono text-slate-400">GROSS LOSS</span>
            <div className="text-sm font-bold text-rose-400 font-mono mt-1">-₹980.00</div>
            <span className="text-[9px] text-slate-500">Market Price Gap</span>
          </div>

          <div className="p-3 rounded bg-black/40 border border-surface-border text-center">
            <span className="text-[10px] font-mono text-slate-400">STT (TAX)</span>
            <div className="text-sm font-bold text-slate-300 font-mono mt-1">-₹25.00</div>
            <span className="text-[9px] text-slate-500">0.025% on Intraday</span>
          </div>

          <div className="p-3 rounded bg-black/40 border border-surface-border text-center">
            <span className="text-[10px] font-mono text-slate-400">NSE TURNOVER</span>
            <div className="text-sm font-bold text-slate-300 font-mono mt-1">-₹3.20</div>
            <span className="text-[9px] text-slate-500">0.00297% Fee</span>
          </div>

          <div className="p-3 rounded bg-black/40 border border-surface-border text-center">
            <span className="text-[10px] font-mono text-slate-400">SEBI + STAMP</span>
            <div className="text-sm font-bold text-slate-300 font-mono mt-1">-₹3.10</div>
            <span className="text-[9px] text-slate-500">₹10/Cr + 0.015%</span>
          </div>

          <div className="p-3 rounded bg-black/40 border border-surface-border text-center">
            <span className="text-[10px] font-mono text-slate-400">GST (18%)</span>
            <div className="text-sm font-bold text-slate-300 font-mono mt-1">-₹32.80</div>
            <span className="text-[9px] text-slate-500">18% on Brokerage</span>
          </div>

          <div className="p-3 rounded bg-black/40 border border-emerald-500/30 text-center bg-emerald-500/5">
            <span className="text-[10px] font-mono text-emerald-400 font-bold">NET IN-POCKET</span>
            <div className="text-sm font-bold text-rose-400 font-mono mt-1">-₹1,044.10</div>
            <span className="text-[9px] text-emerald-500">Actual Realized</span>
          </div>
        </div>
      </div>

      {/* Tomorrow's Disciplined Battle Plan (Sep 25, 2026) */}
      <div className="rounded-lg bg-surface border border-surface-border overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-border flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">Tomorrow&apos;s Pre-Market Battle Plan (Sep 25, 2026)</h3>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Filtered through 3 Quants: Quantitative Council, Multi-Factor Ensemble Alpha Voter, and Hard Risk Sizer.
            </p>
          </div>
          <span className="text-xs font-mono text-sky-400 bg-sky-500/10 px-2 py-0.5 rounded border border-sky-500/20">
            09:45–13:00 IST ENTRY ONLY
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-black/40 text-slate-400 border-b border-surface-border">
              <tr>
                <th className="p-3">Symbol</th>
                <th className="p-3">Order Type</th>
                <th className="p-3">Qty</th>
                <th className="p-3">Target Entry</th>
                <th className="p-3">Stop-Loss</th>
                <th className="p-3">Target</th>
                <th className="p-3">Max Risk</th>
                <th className="p-3">R : R</th>
                <th className="p-3">Strategy</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border text-slate-300">
              {tomorrowPlan.map((p) => (
                <tr key={p.symbol} className="hover:bg-slate-800/30 transition-colors">
                  <td className="p-3 font-bold text-white">{p.symbol}</td>
                  <td className="p-3"><span className="text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded text-[10px]">MIS</span></td>
                  <td className="p-3 text-sky-400">{p.shares}</td>
                  <td className="p-3">{p.entry}</td>
                  <td className="p-3 text-rose-400">{p.sl}</td>
                  <td className="p-3 text-emerald-400">{p.tp}</td>
                  <td className="p-3 text-rose-300">{p.risk}</td>
                  <td className="p-3 text-slate-300 font-bold">{p.rr}</td>
                  <td className="p-3 text-[10px]">
                    {p.strategy.includes("Exploratory") ? (
                      <span className="text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20 font-bold">
                        {p.strategy}
                      </span>
                    ) : (
                      <span className="text-slate-400">{p.strategy}</span>
                    )}
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
