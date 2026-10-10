"""
OMS Project - Streamlit Quant War Room Dashboard
Rapid deployment dashboard for Quant Traders providing real-time P&L tracking,
Risk Heatmaps, Live Order Tape, Pod Management, and Command Center controls.
"""

import time
import requests
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="The War Room - OMS Dashboard",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE_URL = "http://127.0.0.1:8000"

st.title("⚔️ THE WAR ROOM — OMS Monitoring & Control Center")
st.markdown("Real-time telemetry, risk heatmaps, live trading tape, pod management, and administrative emergency controls.")

# Sidebar Auth & Admin Control
st.sidebar.header("🚨 Administrative Control Center")
admin_token = st.sidebar.text_input("Admin Auth Bearer Token", value="admin_secret_war_room_2026", type="password")

if st.sidebar.button("⚡ GLOBAL KILL-SWITCH (EMERGENCY STOP)", type="primary"):
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        r = requests.post(f"{API_BASE_URL}/api/v1/control/kill-switch", json={"active": True}, headers=headers)
        if r.status_code == 200:
            st.sidebar.error("🚨 GLOBAL KILL-SWITCH ACTIVATED! ALL TRADING HALTED.")
        else:
            st.sidebar.warning(f"Auth / API Error: {r.text}")
    except Exception as e:
        st.sidebar.error(f"Failed to connect to Telemetry API: {e}")

if st.sidebar.button("RESET KILL-SWITCH"):
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        r = requests.post(f"{API_BASE_URL}/api/v1/control/kill-switch", json={"active": False}, headers=headers)
        if r.status_code == 200:
            st.sidebar.success("Global Kill-Switch Deactivated. Trading resumed.")
    except Exception as e:
        st.sidebar.error(f"API Error: {e}")

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Algo Pod Management Controls")
# Fetch pod statuses
try:
    pods_res = requests.get(f"{API_BASE_URL}/api/v1/telemetry/pods", timeout=2.0).json().get("pods", {})
except Exception:
    pods_res = {"STRAT_MEAN_REV_001": True, "STRAT_001": True, "STRAT_002": True}

for pod_id, is_active in pods_res.items():
    col_p1, col_p2 = st.sidebar.columns([2, 1])
    col_p1.write(f"**{pod_id}**: {'🟢 ENABLED' if is_active else '🔴 DISABLED'}")
    toggle_target = not is_active
    btn_label = "Enable" if not is_active else "Disable"
    if col_p2.button(btn_label, key=f"btn_pod_{pod_id}"):
        headers = {"Authorization": f"Bearer {admin_token}"}
        try:
            r = requests.post(
                f"{API_BASE_URL}/api/v1/control/pod-toggle",
                json={"strategy_id": pod_id, "enabled": toggle_target},
                headers=headers,
            )
            if r.status_code == 200:
                st.sidebar.success(f"Pod {pod_id} updated to {toggle_target}")
                st.rerun()
            else:
                st.sidebar.error(f"Error: {r.text}")
        except Exception as e:
            st.sidebar.error(f"Failed to connect to API: {e}")

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ Risk Limits Real-Time Form")
max_exposure = st.sidebar.number_input("Max Gross Exposure (₹)", value=1000000.0, step=50000.0)
price_collar = st.sidebar.number_input("Price Collar Deviation (%)", value=2.0, step=0.5)

if st.sidebar.button("Update Risk Limits"):
    headers = {"Authorization": f"Bearer {admin_token}"}
    try:
        r = requests.post(
            f"{API_BASE_URL}/api/v1/control/risk-limits",
            json={"max_gross_exposure": max_exposure, "price_collar_pct": price_collar},
            headers=headers,
        )
        if r.status_code == 200:
            st.sidebar.success("Risk limits updated successfully!")
        else:
            st.sidebar.error(f"Error: {r.text}")
    except Exception as e:
        st.sidebar.error(f"Failed to connect to API: {e}")

# Fetch Telemetry Data
try:
    eq_res = requests.get(f"{API_BASE_URL}/api/v1/telemetry/equity-curve", timeout=2.0).json()
    pos_res = requests.get(f"{API_BASE_URL}/api/v1/telemetry/positions", timeout=2.0).json().get("positions", [])
    health_res = requests.get(f"{API_BASE_URL}/api/v1/telemetry/system-health", timeout=2.0).json()
    recon_res = requests.get(f"{API_BASE_URL}/api/v1/telemetry/reconciliation", timeout=2.0).json()
except Exception as e:
    st.error(f"Telemetry API Connection Warning: Running in offline mode. Details: {e}")
    eq_res = {"total_equity": 100000.0, "total_pnl": 0.0, "pnl_pct": 0.0, "cash_balance": 100000.0, "positions": {}}
    pos_res = []
    health_res = {"kill_switch_active": False, "broker_gateway_status": "HEALTHY", "data_feed_healthy": True, "exchange_connectivity": "CONNECTED"}
    recon_res = {"variance": 0.0, "status": "MATCH"}

# Header Status Badges & Metrics
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Total Account Equity", f"₹{eq_res.get('total_equity', 100000.0):,.2f}")
with col2:
    pnl = eq_res.get("total_pnl", 0.0)
    st.metric("Total P&L", f"₹{pnl:,.2f}", f"{eq_res.get('pnl_pct', 0.0):.2f}%")
with col3:
    st.metric("Cash Balance", f"₹{eq_res.get('cash_balance', 100000.0):,.2f}")
with col4:
    df_healthy = health_res.get("data_feed_healthy", True)
    st.metric("Data Feed Freshness", "HEALTHY (<500ms)" if df_healthy else "STALE (>500ms)", delta="OK" if df_healthy else "HALT", delta_color="normal" if df_healthy else "inverse")
with col5:
    ks = health_res.get("kill_switch_active", False)
    st.metric("Kill-Switch Status", "ACTIVE (HALTED)" if ks else "INACTIVE (OK)", delta="HALTED" if ks else "OK", delta_color="inverse" if ks else "normal")

st.markdown("---")

# Main Dashboard Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Equity & P&L Panel",
    "📦 Live Holdings & Positions",
    "📊 Risk Heatmap",
    "📋 EOD Asset Reconciliation",
    "🛠️ Strategy Factory (Builder)",
    "🧠 Alpha Analyst (Post-Trade Forensics)",
])

with tab1:
    st.subheader("Equity Curve & Account Evolution")
    df = pd.DataFrame({
        "Timestamp": [pd.Timestamp.now() - pd.Timedelta(seconds=i*5) for i in range(10)][::-1],
        "Equity (₹)": [100000.0, 100000.0, 100000.0, 100000.0, 100000.0, 100000.0, 100000.0, 100000.0, 100000.0, eq_res.get("total_equity", 100000.0)]
    })
    st.line_chart(df.set_index("Timestamp"))

with tab2:
    st.subheader("Live Pod Holdings, Entry Prices & Unrealized P&L")
    if pos_res:
        df_pos = pd.DataFrame(pos_res)
        st.dataframe(df_pos, use_container_width=True)
    else:
        st.info("No active open positions currently held across pods.")

with tab3:
    st.subheader("Risk Heatmap & Asset Concentration")
    if pos_res:
        st.write("Active Instrument Exposures:")
        for item in pos_res:
            sym = item.get("symbol", "N/A")
            qty = item.get("quantity", 0.0)
            exp_pct = item.get("exposure_pct", 0.0)
            st.progress(min(1.0, exp_pct / 100.0), text=f"{sym}: {qty} Qty (Total Asset Exposure: {exp_pct}%)")
    else:
        st.info("Zero position concentration risk at present.")

with tab4:
    st.subheader("Broker Ledger vs Paper Exchange Asset Reconciliation")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Broker Ledger State**")
        st.json(recon_res.get("broker_ledger", {}))
    with col_b:
        st.markdown("**Paper Exchange State**")
        st.json(recon_res.get("paper_exchange", {}))

    v = recon_res.get("variance", 0.0)
    if v == 0.0:
        st.success("✅ RECONCILIATION MATCH: VARIANCE = ₹0.00 (Ledger Balance == Paper Exchange Balance)")
    else:
        st.error(f"❌ MISMATCH DETECTED: VARIANCE = ₹{v:,.2f}")

with tab5:
    st.subheader("🛠️ No-Code Strategy Builder & Dynamic Deployment")
    st.markdown("Parameterize strategy blueprints, run instant Time Machine fast-tests with statutory taxes, and deploy pods to the Symmetry Vault.")

    col_cfg1, col_cfg2 = st.columns(2)

    with col_cfg1:
        st.markdown("### 1. Strategy DNA Configuration")
        strat_id_input = st.text_input("Strategy ID", value="STRAT_FACTORY_001")
        blueprint_choice = st.selectbox("Select Strategy Blueprint", ["Mean Reversion", "Trend Following"])
        symbol_choice = st.text_input("Instrument Symbol", value="RELIANCE")

        parameters: dict = {}
        risk_limits: dict = {}

        if blueprint_choice == "Mean Reversion":
            win = st.slider("SMA Window Size", min_value=2, max_value=100, value=20)
            thresh = st.slider("StdDev Threshold (σ)", min_value=0.1, max_value=4.0, value=1.5, step=0.1)
            parameters["window"] = win
            parameters["threshold"] = thresh
            strat_type = "mean_reversion"
        else:
            short_w = st.slider("Short SMA Window", min_value=2, max_value=50, value=5)
            long_w = st.slider("Long SMA Window", min_value=10, max_value=200, value=20)
            parameters["short_window"] = short_w
            parameters["long_window"] = long_w
            strat_type = "trend_following"

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            order_qty = st.number_input("Order Quantity", value=10.0, step=1.0)
            risk_limits["max_qty"] = order_qty
        with col_r2:
            sl_pct = st.number_input("Stop Loss (%)", value=2.0, step=0.5) / 100.0
            risk_limits["stop_loss_pct"] = sl_pct

        init_cap = st.number_input("Initial Capital (₹)", value=100000.0, step=10000.0)

        factory_config = {
            "strategy_id": strat_id_input,
            "strategy_type": strat_type,
            "symbol": symbol_choice,
            "parameters": parameters,
            "risk_limits": risk_limits,
            "allocation": {"initial_capital": init_cap},
        }

        st.json(factory_config)

    with col_cfg2:
        st.markdown("### 2. Time Machine Fast-Test & Verification")
        if st.button("🚀 Run Fast-Test (Time Machine Replay)", type="primary"):
            try:
                r = requests.post(
                    f"{API_BASE_URL}/api/v1/factory/fast-test",
                    json={"config": factory_config, "initial_capital": init_cap, "slippage_bps": 0.0},
                    timeout=10.0,
                )
                if r.status_code == 200:
                    res = r.json()
                    st.session_state["last_fast_test"] = res
                    st.success("Fast-test simulation complete!")
                else:
                    st.error(f"Fast-test API Error: {r.text}")
            except Exception as e:
                # Direct local execution fallback if API is not running standalone
                from oms_project.strategy_factory import FastTestEngine
                res = FastTestEngine.run_fast_test(factory_config, initial_capital=init_cap)
                st.session_state["last_fast_test"] = res
                st.success("Fast-test simulation complete (local fallback engine)!")

        if "last_fast_test" in st.session_state:
            res = st.session_state["last_fast_test"]
            st.markdown("#### 📊 Simulation Results & Statutory Taxes")
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("Final Equity", f"₹{res.get('final_equity', 0.0):,.2f}")
            col_m2.metric("Net P&L", f"₹{res.get('net_pnl', 0.0):,.2f}", f"{res.get('net_pnl_pct', 0.0):.2f}%")
            col_m3.metric("Max Drawdown", f"{res.get('max_drawdown_pct', 0.0):.2f}%")
            col_m4.metric("Total Trades", res.get("total_trades", 0))

            st.markdown("**Indian Statutory Friction Breakdown**")
            st.json(res.get("statutory_friction", {}))

            if res.get("equity_curve"):
                df_eq = pd.DataFrame(res["equity_curve"])
                st.line_chart(df_eq.set_index("timestamp")["equity"])

        st.markdown("---")
        st.markdown("### 3. Deploy to Symmetry Vault")
        if st.button("📥 Deploy Pod to Production"):
            headers = {"Authorization": f"Bearer {admin_token}"}
            try:
                r = requests.post(
                    f"{API_BASE_URL}/api/v1/factory/deploy",
                    json={"config": factory_config},
                    headers=headers,
                    timeout=5.0,
                )
                if r.status_code == 200:
                    st.success(f"Strategy '{strat_id_input}' promoted and deployed to Symmetry Vault!")
                    st.rerun()
                else:
                    st.error(f"Deploy API Error: {r.text}")
            except Exception as e:
                st.error(f"Deploy failed: {e}")

with tab6:
    st.subheader("🧠 Alpha Analyst — Post-Trade Forensics & Diagnostic Brain")
    st.markdown("Automated post-trade autopsy engine detecting regime-loss concentration, execution toxicity, and stop-loss efficiency.")

    col_an1, col_an2 = st.columns([1, 2])

    with col_an1:
        st.markdown("### 🔍 Forensic Control Center")
        if st.button("⚡ Run Full Diagnostic Scan", type="primary"):
            try:
                r = requests.post(f"{API_BASE_URL}/api/v1/analyst/run-analysis", timeout=5.0)
                if r.status_code == 200:
                    st.success("Diagnostic scan completed!")
                    st.session_state["analyst_results"] = r.json().get("results", {})
                else:
                    st.error(f"Analyst API Error: {r.text}")
            except Exception as e:
                from oms_project.alpha_analyst import AlphaAnalyst
                analyst = AlphaAnalyst()
                st.session_state["analyst_results"] = analyst.run_full_diagnostics()
                st.success("Diagnostic scan completed (local fallback)!")

        # Fetch current insights
        try:
            insights_res = requests.get(f"{API_BASE_URL}/api/v1/analyst/insights", timeout=2.0).json()
        except Exception:
            insights_res = st.session_state.get("analyst_results", {"insights": [], "regime_state": "STABLE_TRENDING", "slippage_audit": []})

        st.markdown(f"**Detected Regime State:** `{insights_res.get('regime_state', 'STABLE_TRENDING')}`")
        st.markdown(f"**Active Insights Count:** `{len(insights_res.get('insights', []))}`")

    with col_an2:
        st.markdown("### 💡 Natural Language Diagnostic Insights")
        insights_list = insights_res.get("insights", [])
        if insights_list:
            for ins in insights_list:
                sev_color = "🔴" if ins.get("severity") == "HIGH" else "🟡"
                with st.expander(f"{sev_color} [{ins.get('category')}] {ins.get('headline')}", expanded=True):
                    st.write(f"**Target Strategy:** `{ins.get('strategy_id')}`")
                    st.write(f"**Explanation:** {ins.get('message')}")
                    st.info(f"**💡 Parameter Shift Recommendation:** {ins.get('recommendation')}")
                    confidence = ins.get("confidence_score", 0.8)
                    st.progress(confidence, text=f"Confidence Score: {int(confidence * 100)}%")
        else:
            st.info("Zero negative trade patterns or toxicity detected. Strategy execution is optimal.")

    st.markdown("---")
    st.markdown("### 📉 Execution Toxicity & Slippage Audit Log")
    slippage_audit = insights_res.get("slippage_audit", [])
    if slippage_audit:
        df_slip = pd.DataFrame(slippage_audit)
        st.dataframe(df_slip, use_container_width=True)
    else:
        st.info("No filled execution orders to audit for slippage toxicity.")


