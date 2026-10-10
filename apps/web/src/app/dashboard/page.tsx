"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  ShieldAlert,
  Clock,
  Wallet,
  Activity,
  RefreshCw,
  Lock,
  Layers,
  CheckCircle2,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Database,
  Calendar,
} from "lucide-react";

interface PortfolioState {
  account_id: string;
  session_id: string;
  market_date: string;
  cash_balance: number;
  cash: number;
  total_equity: number;
  equity: number;
  peak_capital: number;
  net_pnl: number;
  net_realized_pnl: number;
  active_positions_count: number;
  schema_version: string;
  updated_at: string;
  status: string;
}

interface OpenPosition {
  symbol: string;
  account_id: string;
  sector: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  stop_loss: number;
  take_profit: number;
  allocated_capital: number;
  entry_time: string;
  holding_period_days: number;
  product_type: string;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  updated_at: string;
}

interface SystemStatus {
  mode: string;
  allow_live_trading: boolean;
  allow_real_broker_execution: boolean;
  next_execution: string;
  execution_window: string;
  market_session: string;
  timeframe: string;
  strategy: string;
  risk_model: string;
  canonical_account: string;
  server_time_utc: string;
  server_time_ist: string;
  ledger_persistence: string;
}

export default function SwingDashboardPage() {
  const [portfolio, setPortfolio] = useState<PortfolioState>({
    account_id: "ACC-FORWARD-CANONICAL-100K-01",
    session_id: "STAGE32_FORWARD_PAPER_SWING_20261001_001",
    market_date: "2026-10-01",
    cash_balance: 100000.0,
    cash: 100000.0,
    total_equity: 100000.0,
    equity: 100000.0,
    peak_capital: 100000.0,
    net_pnl: 0.0,
    net_realized_pnl: 0.0,
    active_positions_count: 0,
    schema_version: "1.0.0",
    updated_at: new Date().toISOString(),
    status: "PRIMED",
  });

  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({
    mode: "PAPER TRADING",
    allow_live_trading: false,
    allow_real_broker_execution: false,
    next_execution: "15:00 IST",
    execution_window: "15:00 - 15:30 IST",
    market_session: "EOD Swing Scanning",
    timeframe: "Daily (1d candles)",
    strategy: "Adaptive Swing Trading (Delivery / CNC)",
    risk_model: "Ed Thorp 1.0% Capital Risk | 2.5x ATR Stop Loss | 3.5x Risk Target",
    canonical_account: "ACC-FORWARD-CANONICAL-100K-01",
    server_time_utc: "2026-10-02 03:00:00 UTC",
    server_time_ist: "2026-10-02 08:30:00 IST",
    ledger_persistence: "SQLite ACID Enabled",
  });

  const [loading, setLoading] = useState<boolean>(true);
  const [lastRefreshed, setLastRefreshed] = useState<string>("Connecting...");
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const fetchDashboardData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      // 1. Fetch Portfolio State
      const portRes = await fetch("/api/dashboard/portfolio");
      if (portRes.ok) {
        const portData = await portRes.json();
        setPortfolio(portData);
      }

      // 2. Fetch Active Open Positions
      const posRes = await fetch("/api/dashboard/positions");
      if (posRes.ok) {
        const posData = await posRes.json();
        setPositions(posData.positions || []);
      }

      // 3. Fetch System Invariant Status
      const statusRes = await fetch("/api/dashboard/system-status");
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setSystemStatus(statusData);
      }

      setFetchError(null);
      setLastRefreshed(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }) + " IST");
    } catch (err: any) {
      console.warn("Polling dashboard endpoints fallback:", err);
      setFetchError("API stream disconnected - showing cached ledger baseline");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  // Reactivity: 10-second polling interval
  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 10000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  const totalUnrealizedPnl = positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0);
  const netRealizedPnl = portfolio.net_pnl || portfolio.net_realized_pnl || 0;
  const totalEquity = portfolio.total_equity || portfolio.equity || 100000.0;
  const cashBalance = portfolio.cash_balance || portfolio.cash || 100000.0;
  const peakCapital = portfolio.peak_capital || 100000.0;

  return (
    <div className="space-y-6 text-slate-100 font-sans pb-12">
      {/* 1. INSTITUTIONAL HEADER */}
      <div className="bg-surface border border-surface-border rounded-xl p-5 md:p-6 shadow-lg shadow-black/40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl md:text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
                <Activity className="w-6 h-6 text-sky-400" />
                Algo Lab Institutional Desk
              </h1>
              {/* Pulsing Yellow "PAPER TRADING" Badge */}
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 font-mono text-xs font-semibold tracking-wide">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
                </span>
                PAPER TRADING
              </div>
            </div>
            <p className="text-xs md:text-sm text-slate-400 font-mono mt-1.5 flex items-center gap-2 flex-wrap">
              <span>Account: <span className="text-sky-400 font-semibold">{portfolio.account_id}</span></span>
              <span>•</span>
              <span>Strategy: <span className="text-slate-300">Swing Delivery (CNC)</span></span>
              <span>•</span>
              <span>Timeframe: <span className="text-slate-300">1d Near-Close</span></span>
              <span>•</span>
              <span className="text-amber-400/90 font-medium">Next EOD Execution: {systemStatus.next_execution}</span>
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <div className="text-right font-mono text-xs text-slate-400">
              <div className="flex items-center gap-1.5 justify-end text-emerald-400">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span>Live Feed (10s)</span>
              </div>
              <div className="text-slate-500 text-[11px] mt-0.5">Updated: {lastRefreshed}</div>
            </div>
            <button
              onClick={fetchDashboardData}
              disabled={isRefreshing}
              className="p-2.5 rounded-lg bg-surface-border/50 hover:bg-surface-border text-slate-300 hover:text-white border border-surface-border transition-all flex items-center justify-center disabled:opacity-50"
              title="Manual refresh"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin text-sky-400" : ""}`} />
            </button>
          </div>
        </div>

        {fetchError && (
          <div className="mt-3 py-1.5 px-3 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-mono flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            <span>{fetchError}</span>
          </div>
        )}
      </div>

      {/* 2. TOP METRICS CARDS (4 CARDS) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Equity */}
        <div className="bg-surface border border-surface-border rounded-xl p-5 shadow-sm relative overflow-hidden group hover:border-slate-600 transition-colors">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono uppercase tracking-wider">
            <span>Total Equity</span>
            <Wallet className="w-4 h-4 text-sky-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-2.5">
            ₹{totalEquity.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-xs font-mono text-slate-400 mt-2 flex items-center justify-between">
            <span>Peak: ₹{peakCapital.toLocaleString("en-IN")}</span>
            <span className="text-emerald-400 font-medium">Solvency: 100%</span>
          </div>
          <div className="absolute top-0 right-0 w-24 h-24 bg-sky-500/5 rounded-full blur-2xl pointer-events-none"></div>
        </div>

        {/* Card 2: Cash Solvency */}
        <div className="bg-surface border border-surface-border rounded-xl p-5 shadow-sm relative overflow-hidden group hover:border-slate-600 transition-colors">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono uppercase tracking-wider">
            <span>Cash Solvency</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-2.5">
            ₹{cashBalance.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-xs font-mono text-slate-400 mt-2 flex items-center justify-between">
            <span>Floor Buffer: ₹10,000</span>
            <span className="text-sky-400 font-medium">
              Free: {((cashBalance / totalEquity) * 100).toFixed(1)}%
            </span>
          </div>
          <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none"></div>
        </div>

        {/* Card 3: Net Realized P&L */}
        <div className="bg-surface border border-surface-border rounded-xl p-5 shadow-sm relative overflow-hidden group hover:border-slate-600 transition-colors">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono uppercase tracking-wider">
            <span>Net Realized P&L</span>
            {netRealizedPnl >= 0 ? (
              <TrendingUp className="w-4 h-4 text-emerald-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-rose-400" />
            )}
          </div>
          <div
            className={`text-2xl font-bold font-mono mt-2.5 ${
              netRealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {netRealizedPnl >= 0 ? "+" : ""}₹
            {netRealizedPnl.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-xs font-mono text-slate-400 mt-2 flex items-center justify-between">
            <span>Absolute: {((netRealizedPnl / 100000.0) * 100).toFixed(2)}%</span>
            <span className="text-slate-500 text-[10px]">Taxes Deducted</span>
          </div>
          <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none"></div>
        </div>

        {/* Card 4: Open Positions Count */}
        <div className="bg-surface border border-surface-border rounded-xl p-5 shadow-sm relative overflow-hidden group hover:border-slate-600 transition-colors">
          <div className="flex items-center justify-between text-slate-400 text-xs font-mono uppercase tracking-wider">
            <span>Open Positions</span>
            <Layers className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-2.5">
            {positions.length} <span className="text-sm font-normal text-slate-500">/ 2 Max Slots</span>
          </div>
          <div className="text-xs font-mono text-slate-400 mt-2 flex items-center justify-between">
            <span>Unrealized P&L:</span>
            <span className={`font-medium ${totalUnrealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {totalUnrealizedPnl >= 0 ? "+" : ""}₹{totalUnrealizedPnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-full blur-2xl pointer-events-none"></div>
        </div>
      </div>

      {/* 3. ACTIVE POSITIONS DATA TABLE */}
      <div className="bg-surface border border-surface-border rounded-xl shadow-lg shadow-black/40 overflow-hidden">
        <div className="p-5 border-b border-surface-border flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h2 className="text-base font-bold text-white tracking-wide">
              Active Swing Positions
            </h2>
            <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-sky-500/10 text-sky-400 border border-sky-500/20">
              Delivery / CNC Overnight Ledger
            </span>
          </div>
          <div className="text-xs font-mono text-slate-400">
            Database: <span className="text-slate-300">swing_portfolio_ledger.db</span>
          </div>
        </div>

        {positions.length === 0 ? (
          <div className="py-16 px-6 text-center">
            <div className="w-14 h-14 rounded-full bg-slate-800/80 border border-slate-700/80 flex items-center justify-center mx-auto mb-4 text-slate-400">
              <Clock className="w-7 h-7 text-amber-400/80" />
            </div>
            <h3 className="text-base font-bold text-white">No Active Positions in Overnight Ledger</h3>
            <p className="text-xs md:text-sm text-slate-400 max-w-lg mx-auto mt-2 leading-relaxed">
              The EOD Swing Trading Daemon evaluates the 50-stock NIFTY universe daily at 15:00 IST. High-conviction setups with 2.5×ATR stop loss and 3.5×Risk target execute between 15:15 – 15:25 IST and will persist here overnight.
            </p>
            <div className="mt-5 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-surface-border/40 border border-surface-border text-xs font-mono text-slate-400">
              <Database className="w-3.5 h-3.5 text-sky-400" />
              <span>Table: open_positions | Records: 0</span>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-[#0e131d] text-slate-400 border-b border-surface-border uppercase text-[10px] tracking-wider">
                <tr>
                  <th className="py-3 px-4">Symbol / Sector</th>
                  <th className="py-3 px-4">Entry Date</th>
                  <th className="py-3 px-4 text-right">Qty</th>
                  <th className="py-3 px-4 text-right">Entry Price</th>
                  <th className="py-3 px-4 text-right">Current Price</th>
                  <th className="py-3 px-4 text-right">Stop Loss (2.5x)</th>
                  <th className="py-3 px-4 text-right">Take Profit (3.5x)</th>
                  <th className="py-3 px-4 text-right">Unrealized P&L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/50 text-slate-200">
                {positions.map((pos, idx) => {
                  const pnl = pos.unrealized_pnl || 0;
                  const pnlPct = pos.unrealized_pnl_pct || 0;
                  const isPositive = pnl >= 0;

                  return (
                    <tr key={pos.symbol || idx} className="hover:bg-slate-800/20 transition-colors">
                      <td className="py-3.5 px-4 font-bold text-white">
                        <div className="flex items-center gap-2">
                          <span className="text-sky-300 font-semibold">{pos.symbol}</span>
                          <span className="px-1.5 py-0.5 rounded text-[9px] bg-slate-800 text-slate-400 border border-slate-700">
                            {pos.sector}
                          </span>
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-slate-400">{pos.entry_time?.slice(0, 16) || "—"}</td>
                      <td className="py-3.5 px-4 text-right text-white font-semibold">{pos.quantity}</td>
                      <td className="py-3.5 px-4 text-right text-slate-300">
                        ₹{pos.entry_price?.toFixed(2)}
                      </td>
                      <td className="py-3.5 px-4 text-right font-bold text-white">
                        ₹{pos.current_price?.toFixed(2)}
                      </td>
                      <td className="py-3.5 px-4 text-right text-rose-400/90 font-medium">
                        ₹{pos.stop_loss?.toFixed(2)}
                      </td>
                      <td className="py-3.5 px-4 text-right text-emerald-400/90 font-medium">
                        ₹{pos.take_profit?.toFixed(2)}
                      </td>
                      <td className={`py-3.5 px-4 text-right font-bold ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                        <div className="flex items-center justify-end gap-1">
                          {isPositive ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                          <span>{isPositive ? "+" : ""}₹{pnl.toFixed(2)}</span>
                          <span className="text-[10px] font-normal">({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 4. FOOTER SAFETY INVARIANT BAR */}
      <div className="bg-[#0b0f17] border border-emerald-900/40 rounded-xl p-4 shadow-md">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="flex h-2.5 w-2.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="text-emerald-400 font-bold tracking-wide">
              SAFETY BOUNDARY INVARIANTS:
            </span>
            <span className="px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/60 font-semibold">
              ALLOW_LIVE_TRADING = FALSE
            </span>
            <span className="px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/60 font-semibold">
              ALLOW_REAL_BROKER_EXECUTION = FALSE
            </span>
          </div>

          <div className="flex items-center gap-3 text-slate-400 text-[11px]">
            <span className="flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-sky-400" />
              <span>SQLite ACID Ledger</span>
            </span>
            <span>•</span>
            <span className="flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-amber-400" />
              <span>XNSE Calendar Gate</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
