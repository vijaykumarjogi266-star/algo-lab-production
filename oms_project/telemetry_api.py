"""
OMS Project - Telemetry & Management API ("The War Room Backend")
Asynchronous Read-Only Telemetry & Secured Administrative Control API.
"""

import time
import json
import asyncio
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect, Security
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from oms_project.schemas import OrderState
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.cio_manager import CIOManager
from oms_project.strategy_factory import StrategyFactory, FastTestEngine, StrategyConfig
from oms_project.strategies.mean_reversion.strategy_sdk import StrategySDK
from oms_project.alpha_analyst import AlphaAnalyst
from oms_project.auto_tuner import AutoTuner
from oms_project.scripts.reconciliation import AssetReconciler

ADMIN_BEARER_TOKEN = "admin_secret_war_room_2026"

app = FastAPI(
    title="OMS War Room Telemetry & Control API",
    description="Real-time Monitoring & Command Center for OMS Ecosystem",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global reference to BrokerGateway singleton
_gateway_instance: Optional[BrokerGateway] = None
_paper_exchange_instance: Optional[PaperExchange] = None
_cio_manager_instance: Optional[CIOManager] = None
_alpha_analyst_instance: Optional[AlphaAnalyst] = None
_auto_tuner_instance: Optional[AutoTuner] = None
_deployed_configs: Dict[str, Dict[str, Any]] = {}
_live_event_queue: asyncio.Queue = asyncio.Queue()


def get_gateway() -> BrokerGateway:
    global _gateway_instance, _paper_exchange_instance
    if _gateway_instance is None:
        _paper_exchange_instance = PaperExchange(initial_cash=100000.0)
        _gateway_instance = BrokerGateway(paper_exchange=_paper_exchange_instance)
        _gateway_instance.strategy_balances["STRAT_MEAN_REV_001"] = 100000.0

        # Wire state transition listener for live tape
        def on_pos_update(strat_id, symbol, pos, cash):
            event = {
                "timestamp": time.time(),
                "event": "POSITION_UPDATE",
                "strategy_id": strat_id,
                "symbol": symbol,
                "position": pos,
                "cash": cash,
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_live_event_queue.put(event))
            except RuntimeError:
                pass

        def on_order_transition(order_event):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_live_event_queue.put(order_event))
            except RuntimeError:
                pass

        _gateway_instance.subscribe_position_updates(on_pos_update)
        _gateway_instance.subscribe_order_transitions(on_order_transition)

    return _gateway_instance


def get_cio_manager(gw: BrokerGateway = Depends(get_gateway)) -> CIOManager:
    global _cio_manager_instance
    if _cio_manager_instance is None:
        _cio_manager_instance = CIOManager(gateway=gw)
    return _cio_manager_instance


def get_alpha_analyst(gw: BrokerGateway = Depends(get_gateway)) -> AlphaAnalyst:
    global _alpha_analyst_instance
    if _alpha_analyst_instance is None:
        _alpha_analyst_instance = AlphaAnalyst(db=gw.db, gateway=gw)
    return _alpha_analyst_instance


def get_auto_tuner(analyst: AlphaAnalyst = Depends(get_alpha_analyst)) -> AutoTuner:
    global _auto_tuner_instance
    if _auto_tuner_instance is None:
        _auto_tuner_instance = AutoTuner(analyst=analyst)
    return _auto_tuner_instance


def verify_admin_auth(authorization: str = Header(..., description="Bearer admin_secret_war_room_2026")):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    token = authorization.replace("Bearer ", "").strip()
    if token != ADMIN_BEARER_TOKEN:
        raise HTTPException(status_code=403, detail="FORBIDDEN: Invalid Administrative Token")
    return True


# ------------------------------------------------------------------------------
# 1. TELEMETRY ENDPOINTS (READ-ONLY)
# ------------------------------------------------------------------------------

@app.get("/api/v1/telemetry/equity-curve")
def get_equity_curve(gw: BrokerGateway = Depends(get_gateway)):
    """Returns aggregated P&L and total equity time-series."""
    market_prices = gw.reference_market_prices
    strat_id = "STRAT_MEAN_REV_001"

    total_assets = gw.get_broker_ledger_total_assets(strategy_id=strat_id)
    cash = gw.strategy_balances.get(strat_id, 0.0)
    reserved = gw.strategy_reserved.get(strat_id, 0.0)
    pos_dict = gw.strategy_positions.get(strat_id, {})

    pnl = total_assets - 100000.0  # Initial capital = 100,000

    return {
        "timestamp": time.time(),
        "strategy_id": strat_id,
        "initial_capital": 100000.0,
        "total_equity": round(total_assets, 2),
        "total_pnl": round(pnl, 2),
        "pnl_pct": round((pnl / 100000.0) * 100.0, 2),
        "cash_balance": round(cash, 2),
        "reserved_balance": round(reserved, 2),
        "positions": pos_dict,
    }


@app.get("/api/v1/telemetry/positions")
def get_live_positions(gw: BrokerGateway = Depends(get_gateway)):
    """Returns current holdings, average entry prices, market values, exposure %, and unrealized P&L for all pods."""
    res = []
    total_assets_all = max(1.0, sum(gw.get_broker_ledger_total_assets(s) for s in gw.strategy_balances.keys()))
    for strat_id, pos_map in gw.strategy_positions.items():
        entry_map = gw.strategy_entry_prices.get(strat_id, {})
        for symbol, qty in pos_map.items():
            if qty == 0:
                continue
            ref_price = gw.reference_market_prices.get(symbol, 0.0)
            avg_entry = entry_map.get(symbol, ref_price)
            mkt_val = qty * ref_price
            unrealized_pnl = qty * (ref_price - avg_entry)
            exposure_pct = round((abs(mkt_val) / total_assets_all) * 100.0, 2)
            res.append({
                "strategy_id": strat_id,
                "symbol": symbol,
                "quantity": qty,
                "avg_entry_price": round(avg_entry, 2),
                "market_price": round(ref_price, 2),
                "market_value": round(mkt_val, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "exposure_pct": exposure_pct,
            })
    return {"positions": res}


@app.get("/api/v1/telemetry/pods")
def get_pod_statuses(gw: BrokerGateway = Depends(get_gateway)):
    """Returns enabled/disabled status of all registered Algo Pods."""
    return {"pods": gw.pod_enabled}


@app.get("/api/v1/telemetry/system-health")
def get_system_health(gw: BrokerGateway = Depends(get_gateway)):
    """Reports status of Data Feed (Heartbeat latency), Kill-Switch, and Gateway."""
    now = time.time()
    max_ts = max(gw.reference_market_timestamps.values()) if gw.reference_market_timestamps else now
    staleness_ms = max(0.0, (now - max_ts) * 1000.0)

    is_data_feed_healthy = staleness_ms <= gw.max_market_data_staleness_ms

    return {
        "timestamp": now,
        "kill_switch_active": gw.kill_switch_active,
        "database_reachable": gw.db_reachable,
        "data_feed_healthy": is_data_feed_healthy,
        "data_feed_staleness_ms": round(staleness_ms, 2),
        "max_staleness_limit_ms": gw.max_market_data_staleness_ms,
        "exchange_connectivity": "CONNECTED",
        "broker_gateway_status": "HALTED_KILL_SWITCH" if gw.kill_switch_active else ("HEALTHY" if is_data_feed_healthy else "STALE_DATA_HALT"),
    }


@app.get("/api/v1/telemetry/reconciliation")
def get_asset_reconciliation(gw: BrokerGateway = Depends(get_gateway)):
    """Runs EOD Asset Reconciliation comparing Broker Ledger vs Paper Exchange."""
    reconciler = AssetReconciler(gw, gw.paper_exchange)
    report = reconciler.run_reconciliation("STRAT_MEAN_REV_001")
    return report


@app.get("/api/v1/telemetry/live-tape/sse")
async def live_tape_sse():
    """Server-Sent Events stream pushing real-time order execution events."""
    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(_live_event_queue.get(), timeout=2.0)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                hb = {"timestamp": time.time(), "event": "PING"}
                yield f"data: {json.dumps(hb)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.websocket("/api/v1/telemetry/live-tape/ws")
async def live_tape_ws(websocket: WebSocket):
    """WebSocket stream pushing real-time order state transitions and live tape updates."""
    await websocket.accept()
    try:
        while True:
            event = await _live_event_queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass


# ------------------------------------------------------------------------------
# 2. CONTROL CENTER ENDPOINTS (SECURED WITH ADMIN AUTH)
# ------------------------------------------------------------------------------

class KillSwitchRequest(BaseModel):
    active: bool = Field(..., description="True to activate Kill Switch, False to deactivate")


class PodToggleRequest(BaseModel):
    strategy_id: str
    enabled: bool


class RiskLimitsRequest(BaseModel):
    max_gross_exposure: float = Field(..., gt=0)
    price_collar_pct: float = Field(..., gt=0, le=20.0)


@app.post("/api/v1/control/kill-switch")
def toggle_kill_switch(
    req: KillSwitchRequest,
    gw: BrokerGateway = Depends(get_gateway),
    authenticated: bool = Depends(verify_admin_auth),
):
    """Activates or deactivates the Global Emergency Stop Kill-Switch."""
    gw.set_kill_switch(req.active)
    status_str = "ACTIVE (ALL TRADING HALTED)" if req.active else "INACTIVE (TRADING ALLOWED)"
    return {
        "success": True,
        "message": f"Global Kill-Switch updated to {status_str}",
        "kill_switch_active": gw.kill_switch_active,
        "timestamp": time.time(),
    }


@app.post("/api/v1/control/pod-toggle")
def toggle_pod_status(
    req: PodToggleRequest,
    gw: BrokerGateway = Depends(get_gateway),
    authenticated: bool = Depends(verify_admin_auth),
):
    """Enables or Disables a specific Algo Pod in real-time without container restart."""
    gw.set_pod_enabled(req.strategy_id, req.enabled)
    status_str = "ENABLED" if req.enabled else "DISABLED"
    return {
        "success": True,
        "message": f"Algo Pod '{req.strategy_id}' updated to {status_str}",
        "strategy_id": req.strategy_id,
        "enabled": req.enabled,
        "timestamp": time.time(),
    }


@app.post("/api/v1/control/risk-limits")
def adjust_risk_limits(
    req: RiskLimitsRequest,
    gw: BrokerGateway = Depends(get_gateway),
    authenticated: bool = Depends(verify_admin_auth),
):
    """Adjusts MaxGrossExposure and PriceCollar in real-time."""
    gw.max_gross_exposure = req.max_gross_exposure
    gw.price_collar_pct = req.price_collar_pct
    return {
        "success": True,
        "message": f"Risk Limits updated: MaxGrossExposure=₹{req.max_gross_exposure:,.2f}, PriceCollar={req.price_collar_pct}%",
        "max_gross_exposure": gw.max_gross_exposure,
        "price_collar_pct": gw.price_collar_pct,
        "timestamp": time.time(),
    }


# ------------------------------------------------------------------------------
# 3. STRATEGY FACTORY ENDPOINTS (PROJECT STRAT-FACTORY)
# ------------------------------------------------------------------------------

class FastTestRequest(BaseModel):
    config: Dict[str, Any]
    initial_capital: float = 100000.0
    slippage_bps: float = 0.0


class DeployStrategyRequest(BaseModel):
    config: Dict[str, Any]


class HotReloadRequest(BaseModel):
    strategy_id: str
    parameters: Dict[str, Any]


@app.get("/api/v1/factory/blueprints")
def get_blueprints():
    """Returns metadata schema for all available strategy blueprints."""
    return {"blueprints": StrategyFactory.get_registered_blueprints()}


@app.get("/api/v1/factory/deployed")
def get_deployed_strategies():
    """Returns list of currently deployed strategy configurations."""
    return {"deployed_strategies": _deployed_configs}


@app.post("/api/v1/factory/fast-test")
async def execute_fast_test(req: FastTestRequest):
    """
    Executes high-speed deterministic historical replay in the Time Machine.
    Applies exact Indian statutory taxes and friction.
    """
    async with FastTestEngine._semaphore:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            FastTestEngine.run_fast_test,
            req.config,
            None,
            req.initial_capital,
            req.slippage_bps,
        )
        return res


@app.post("/api/v1/factory/deploy")
def deploy_strategy(
    req: DeployStrategyRequest,
    gw: BrokerGateway = Depends(get_gateway),
    authenticated: bool = Depends(verify_admin_auth),
):
    """
    Promotes a strategy configuration from simulation to production execution.
    Registers the pod with CIO Manager and updates Gateway balance tracking.
    """
    config = req.config
    strat_id = config.get("strategy_id")
    if not strat_id:
        raise HTTPException(status_code=400, detail="Missing 'strategy_id' in strategy config")

    sdk = StrategySDK(strategy_id=strat_id)
    strat_instance = StrategyFactory.instantiate(config, sdk=sdk)

    allocation = config.get("allocation", {})
    init_cap = float(allocation.get("initial_capital", 100000.0))

    gw.strategy_balances[strat_id] = init_cap
    gw.set_pod_enabled(strat_id, True)

    cio = get_cio_manager(gw)
    cio.register_pod(strat_id, strat_instance)
    cio.rebalance_allocations()

    _deployed_configs[strat_id] = config

    return {
        "success": True,
        "message": f"Strategy pod '{strat_id}' successfully deployed to Symmetry Vault.",
        "strategy_id": strat_id,
        "enabled": True,
        "allocated_capital": gw.strategy_balances.get(strat_id, init_cap),
        "timestamp": time.time(),
    }


@app.post("/api/v1/factory/hot-reload")
def hot_reload_parameters(
    req: HotReloadRequest,
    gw: BrokerGateway = Depends(get_gateway),
    authenticated: bool = Depends(verify_admin_auth),
):
    """
    Hot-reloads parameter configurations of an active strategy pod in real-time.
    """
    strat_id = req.strategy_id
    if strat_id not in _deployed_configs:
        raise HTTPException(status_code=404, detail=f"Strategy pod '{strat_id}' is not currently deployed.")

    config = _deployed_configs[strat_id]
    config.setdefault("parameters", {}).update(req.parameters)

    cio = get_cio_manager(gw)
    instance = cio.registered_pods.get(strat_id)
    if instance:
        for k, v in req.parameters.items():
            if hasattr(instance, k):
                setattr(instance, k, v)
            if hasattr(instance, "window_size") and k in ("window", "window_size"):
                instance.window_size = int(v)
            if hasattr(instance, "std_dev_threshold") and k in ("threshold", "std_dev_threshold"):
                instance.std_dev_threshold = float(v)

    return {
        "success": True,
        "message": f"Parameters for strategy pod '{strat_id}' hot-reloaded successfully.",
        "strategy_id": strat_id,
        "updated_parameters": config["parameters"],
        "timestamp": time.time(),
    }


# ------------------------------------------------------------------------------
# 4. ALPHA ANALYST ENDPOINTS (PROJECT ADAPT - WAVE 1)
# ------------------------------------------------------------------------------

@app.get("/api/v1/analyst/insights")
def get_analyst_insights(analyst: AlphaAnalyst = Depends(get_alpha_analyst)):
    """Returns active diagnostic insights, regime state, and toxic slippage audit."""
    if not analyst.last_analysis_timestamp:
        analyst.run_full_diagnostics()
    return {
        "timestamp": analyst.last_analysis_timestamp,
        "regime_state": "HIGH_VOLATILITY_MORNING" if analyst.insights else "STABLE_TRENDING",
        "insights_count": len(analyst.insights),
        "insights": [i.model_dump() for i in analyst.insights],
        "slippage_audit": [s.model_dump() for s in analyst.slippage_records],
    }


@app.post("/api/v1/analyst/run-analysis")
def trigger_analysis(analyst: AlphaAnalyst = Depends(get_alpha_analyst)):
    """Triggers an immediate read-only forensic analysis over the order ledger."""
    res = analyst.run_full_diagnostics()
    return {
        "success": True,
        "message": f"Forensic analysis completed. Identified {res['insights_count']} diagnostic insights.",
        "results": res,
    }


# ------------------------------------------------------------------------------
# 5. AUTO-TUNER ENDPOINTS (PROJECT ADAPT - WAVE 2)
# ------------------------------------------------------------------------------

class VerifySuggestionRequest(BaseModel):
    insight: Dict[str, Any]
    base_config: Dict[str, Any]
    initial_capital: float = 100000.0


class AutoOptimizeRequest(BaseModel):
    base_config: Dict[str, Any]
    initial_capital: float = 100000.0


@app.post("/api/v1/tuner/verify-suggestion")
def verify_suggestion(
    req: VerifySuggestionRequest,
    tuner: AutoTuner = Depends(get_auto_tuner),
):
    """
    Runs Time Machine simulation proof comparing baseline config vs candidate parameter shift.
    """
    result = tuner.verify_insight_recommendation(
        insight=req.insight,
        base_config=req.base_config,
        initial_capital=req.initial_capital,
    )
    return result.model_dump()


@app.post("/api/v1/tuner/auto-optimize")
def auto_optimize_strategy(
    req: AutoOptimizeRequest,
    tuner: AutoTuner = Depends(get_auto_tuner),
):
    """
    Sweeps parameter grid around strategy in Time Machine and returns top 3 verified configurations.
    """
    res = tuner.auto_optimize_strategy(
        base_config=req.base_config,
        initial_capital=req.initial_capital,
    )
    return res


# ------------------------------------------------------------------------------
# 6. WAR ROOM FRONTEND DASHBOARD HTML SERVING
# ------------------------------------------------------------------------------

WAR_ROOM_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The War Room - OMS Monitoring & Control Center</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-dark: #0d1117;
            --panel-bg: #161b22;
            --accent-green: #238636;
            --accent-red: #da3633;
            --accent-blue: #58a6ff;
            --text-primary: #c9d1d9;
            --text-heading: #f0f6fc;
            --border-color: #30363d;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            margin: 0;
            padding: 20px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 15px;
            margin-bottom: 20px;
        }
        .header h1 {
            color: var(--text-heading);
            margin: 0;
            font-size: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: bold;
            display: inline-block;
            margin-left: 6px;
        }
        .badge-green { background-color: rgba(35, 134, 54, 0.2); color: #3fb950; border: 1px solid #238636; }
        .badge-red { background-color: rgba(218, 54, 51, 0.2); color: #f85149; border: 1px solid #da3633; }
        .badge-blue { background-color: rgba(88, 166, 255, 0.2); color: #58a6ff; border: 1px solid #1f6feb; }
        
        .grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
        }
        .card {
            background-color: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .card h2 {
            color: var(--text-heading);
            font-size: 16px;
            margin-top: 0;
            margin-bottom: 15px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
        }
        .metrics-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
        }
        .metric-box {
            background-color: rgba(255,255,255,0.03);
            padding: 12px 18px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            flex: 1;
            margin-right: 10px;
        }
        .metric-box:last-child { margin-right: 0; }
        .metric-label { font-size: 12px; color: #8b949e; }
        .metric-value { font-size: 20px; font-weight: bold; color: var(--text-heading); margin-top: 5px; }

        .kill-btn {
            width: 100%;
            padding: 14px;
            font-size: 16px;
            font-weight: bold;
            color: white;
            background-color: var(--accent-red);
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .kill-btn:hover { opacity: 0.85; }
        .form-group {
            margin-bottom: 12px;
        }
        .form-group label { display: block; font-size: 12px; margin-bottom: 4px; color: #8b949e; }
        .form-group input {
            width: 100%;
            padding: 8px;
            box-sizing: border-box;
            background: #0d1117;
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            border-radius: 4px;
        }
        .btn-secondary {
            background-color: #21262d;
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            width: 100%;
        }
        .btn-secondary:hover { background-color: #30363d; }
        .btn-sm {
            padding: 4px 10px;
            font-size: 12px;
            border-radius: 4px;
            border: 1px solid var(--border-color);
            cursor: pointer;
            background: #21262d;
            color: var(--text-primary);
        }
        
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border-color); }
        th { color: #8b949e; font-weight: 600; }
        .pod-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #21262d; }
    </style>
</head>
<body>

    <div class="header">
        <h1>⚔️ THE WAR ROOM <span>OMS Monitoring & Control Center</span></h1>
        <div>
            <span id="exch-status" class="status-badge badge-blue">EXCHANGE: CONNECTED</span>
            <span id="data-status" class="status-badge badge-green">DATA FEED: HEALTHY</span>
            <span id="gateway-status" class="status-badge badge-green">GATEWAY: HEALTHY</span>
            <span id="killswitch-status" class="status-badge badge-green">KILL-SWITCH: INACTIVE</span>
        </div>
    </div>

    <div class="grid">
        <!-- Left Column: P&L Chart & Live Trading Tape -->
        <div>
            <div class="card">
                <h2>📈 Real-Time Equity Curve & Strategy P&L</h2>
                <div class="metrics-row">
                    <div class="metric-box">
                        <div class="metric-label">TOTAL EQUITY</div>
                        <div id="val-total-equity" class="metric-value">₹100,000.00</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">TOTAL P&L</div>
                        <div id="val-pnl" class="metric-value" style="color: #3fb950;">+₹0.00 (0.00%)</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-label">CASH BALANCE</div>
                        <div id="val-cash" class="metric-value">₹100,000.00</div>
                    </div>
                </div>
                <canvas id="equityChart" height="110"></canvas>
            </div>

            <div class="card">
                <h2>📜 The Live Tape (Order Execution & State Stream)</h2>
                <div style="max-height: 250px; overflow-y: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Timestamp</th>
                                <th>Event Type</th>
                                <th>Strategy</th>
                                <th>Symbol</th>
                                <th>State / Details</th>
                            </tr>
                        </thead>
                        <tbody id="tape-rows">
                            <tr><td colspan="5" style="text-align:center; color:#8b949e;">Waiting for live order executions...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Right Column: Command Center & Health Indicators -->
        <div>
            <div class="card" style="border: 2px solid var(--accent-red);">
                <h2 style="color: #f85149;">🚨 COMMAND CENTER (ADMIN)</h2>
                <div class="form-group">
                    <label>ADMIN AUTH TOKEN</label>
                    <input type="password" id="admin-token" value="admin_secret_war_room_2026">
                </div>
                <button id="btn-kill-switch" class="kill-btn" onclick="toggleKillSwitch()">⚡ GLOBAL KILL-SWITCH (EMERGENCY STOP)</button>
            </div>

            <div class="card">
                <h2>🤖 Algo Pod Management</h2>
                <div id="pod-controls-container">
                    <div style="text-align:center; color:#8b949e;">Loading pod statuses...</div>
                </div>
            </div>

            <div class="card">
                <h2>🛡️ Risk Limit Adjustment</h2>
                <div class="form-group">
                    <label>MAX GROSS EXPOSURE (₹)</label>
                    <input type="number" id="input-max-exposure" value="1000000">
                </div>
                <div class="form-group">
                    <label>PRICE COLLAR DEVIATION (%)</label>
                    <input type="number" id="input-price-collar" value="2.0" step="0.1">
                </div>
                <button class="btn-secondary" onclick="updateRiskLimits()">Update Risk Limits</button>
            </div>

            <div class="card">
                <h2>📊 Risk Heatmap & Asset Concentration</h2>
                <div id="risk-heatmap">
                    <div style="font-size: 13px; color: #8b949e;">No active open position concentration.</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const chartCtx = document.getElementById('equityChart').getContext('2d');
        const equityChart = new Chart(chartCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Total Account Equity (₹)',
                    data: [],
                    borderColor: '#3fb950',
                    backgroundColor: 'rgba(63, 185, 80, 0.1)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
                    y: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } }
                }
            }
        });

        async function fetchTelemetry() {
            try {
                const resEq = await fetch('/api/v1/telemetry/equity-curve');
                const dataEq = await resEq.json();
                
                document.getElementById('val-total-equity').innerText = '₹' + dataEq.total_equity.toLocaleString();
                document.getElementById('val-pnl').innerText = (dataEq.total_pnl >= 0 ? '+' : '') + '₹' + dataEq.total_pnl.toFixed(2) + ' (' + dataEq.pnl_pct.toFixed(2) + '%)';
                document.getElementById('val-cash').innerText = '₹' + dataEq.cash_balance.toLocaleString();

                const nowStr = new Date().toLocaleTimeString();
                if (equityChart.data.labels.length > 20) {
                    equityChart.data.labels.shift();
                    equityChart.data.datasets[0].data.shift();
                }
                equityChart.data.labels.push(nowStr);
                equityChart.data.datasets[0].data.push(dataEq.total_equity);
                equityChart.update();

                const resHealth = await fetch('/api/v1/telemetry/system-health');
                const dataHealth = await resHealth.json();

                const gwBadge = document.getElementById('gateway-status');
                gwBadge.innerText = 'GATEWAY: ' + dataHealth.broker_gateway_status;
                gwBadge.className = 'status-badge ' + (dataHealth.broker_gateway_status === 'HEALTHY' ? 'badge-green' : 'badge-red');

                const killBadge = document.getElementById('killswitch-status');
                killBadge.innerText = 'KILL-SWITCH: ' + (dataHealth.kill_switch_active ? 'ACTIVE (HALTED)' : 'INACTIVE');
                killBadge.className = 'status-badge ' + (dataHealth.kill_switch_active ? 'badge-red' : 'badge-green');

                const dataBadge = document.getElementById('data-status');
                dataBadge.innerText = 'DATA FEED: ' + (dataHealth.data_feed_healthy ? 'HEALTHY' : 'STALE HALT');
                dataBadge.className = 'status-badge ' + (dataHealth.data_feed_healthy ? 'badge-green' : 'badge-red');

                // Update Risk Heatmap & Positions
                const resPos = await fetch('/api/v1/telemetry/positions');
                const dataPos = await resPos.json();
                const heatmapDiv = document.getElementById('risk-heatmap');
                if (dataPos.positions && dataPos.positions.length > 0) {
                    let html = '';
                    dataPos.positions.forEach(p => {
                        html += `
                        <div style="margin-bottom: 10px;">
                            <div style="display:flex; justify-content:space-between; font-size:12px;">
                                <span><strong>${p.symbol}</strong> (${p.strategy_id}): ${p.quantity} Qty @ ₹${p.avg_entry_price}</span>
                                <span>Exposure: <strong>${p.exposure_pct}%</strong></span>
                            </div>
                            <div style="background:#21262d; border-radius:4px; height:8px; margin-top:4px;">
                                <div style="background:${p.exposure_pct > 30 ? '#da3633' : '#3fb950'}; width:${Math.min(100, p.exposure_pct)}%; height:100%; border-radius:4px;"></div>
                            </div>
                        </div>`;
                    });
                    heatmapDiv.innerHTML = html;
                } else {
                    heatmapDiv.innerHTML = '<div style="font-size: 13px; color: #8b949e;">No active open positions currently held.</div>';
                }

                // Fetch Pod Controls
                const resPods = await fetch('/api/v1/telemetry/pods');
                const dataPods = await resPods.json();
                const podDiv = document.getElementById('pod-controls-container');
                let podHtml = '';
                for (const [podId, isEnabled] of Object.entries(dataPods.pods)) {
                    podHtml += `
                    <div class="pod-row">
                        <div>
                            <strong>${podId}</strong>
                            <span class="status-badge ${isEnabled ? 'badge-green' : 'badge-red'}" style="font-size:11px; padding:3px 8px;">${isEnabled ? 'ENABLED' : 'DISABLED'}</span>
                        </div>
                        <button class="btn-sm" onclick="togglePod('${podId}', ${!isEnabled})">${isEnabled ? 'Disable' : 'Enable'}</button>
                    </div>`;
                }
                podDiv.innerHTML = podHtml;

            } catch (err) {
                console.error('Telemetry update failed', err);
            }
        }

        setInterval(fetchTelemetry, 2000);
        fetchTelemetry();

        // Connect SSE Live Tape
        const sse = new EventSource('/api/v1/telemetry/live-tape/sse');
        sse.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.event === 'PING') return;
            const tbody = document.getElementById('tape-rows');
            if (tbody.children.length === 1 && tbody.children[0].innerText.includes('Waiting')) {
                tbody.innerHTML = '';
            }
            const tr = document.createElement('tr');
            const dt = new Date(data.timestamp * 1000).toLocaleTimeString();
            if (data.event === 'ORDER_TRANSITION') {
                tr.innerHTML = `<td>${dt}</td><td><span style="color:#58a6ff;">ORDER_${data.state}</span></td><td>${data.strategy_id}</td><td>${data.symbol}</td><td>${data.side} ${data.qty} @ ₹${data.price} (${data.message})</td>`;
            } else if (data.event === 'POSITION_UPDATE') {
                tr.innerHTML = `<td>${dt}</td><td><span style="color:#3fb950;">POS_UPDATE</span></td><td>${data.strategy_id}</td><td>${data.symbol}</td><td>Position: ${data.position} | Cash: ₹${data.cash.toLocaleString()}</td>`;
            }
            tbody.insertBefore(tr, tbody.firstChild);
        };

        async function toggleKillSwitch() {
            const token = document.getElementById('admin-token').value;
            const res = await fetch('/api/v1/control/kill-switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify({ active: true })
            });
            const data = await res.json();
            alert(data.message || JSON.stringify(data));
            fetchTelemetry();
        }

        async function togglePod(strategyId, enable) {
            const token = document.getElementById('admin-token').value;
            const res = await fetch('/api/v1/control/pod-toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify({ strategy_id: strategyId, enabled: enable })
            });
            const data = await res.json();
            alert(data.message || JSON.stringify(data));
            fetchTelemetry();
        }

        async function updateRiskLimits() {
            const token = document.getElementById('admin-token').value;
            const maxExp = parseFloat(document.getElementById('input-max-exposure').value);
            const priceCollar = parseFloat(document.getElementById('input-price-collar').value);
            const res = await fetch('/api/v1/control/risk-limits', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify({ max_gross_exposure: maxExp, price_collar_pct: priceCollar })
            });
            const data = await res.json();
            alert(data.message || JSON.stringify(data));
        }
    </script>
</body>
</html>
"""

@app.get("/dashboard", response_class=HTMLResponse)
def serve_war_room_dashboard():
    """Serves the interactive War Room visual dashboard UI."""
    return HTMLResponse(content=WAR_ROOM_HTML)

