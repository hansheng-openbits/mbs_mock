# ui_app.py
import streamlit as st
import requests
from requests.exceptions import RequestException
import json
import pandas as pd

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="RMBS Platform", layout="wide")

st.title("🏦 Enterprise RMBS Platform")

# --- Helpers ---
def fetch_deals():
    try:
        res = requests.get(f"{API_URL}/deals", timeout=5)
        if res.status_code == 200:
            return res.json().get("deals", [])
    except RequestException:
        st.warning("API server not reachable. Start FastAPI at 127.0.0.1:8000.")
    return []

def fetch_model_registry():
    try:
        res = requests.get(f"{API_URL}/models/registry", timeout=5)
        if res.status_code == 200:
            return res.json().get("registry", {})
    except RequestException:
        pass
    return {}

# Sidebar: Persona Selection
persona = st.sidebar.selectbox(
    "Select Persona",
    ["Arranger (Structurer)", "Servicer (Operations)", "Investor (Analytics)"]
)

if persona == "Arranger (Structurer)":
    st.header("Deal Structuring Workbench")
    
    deal_id_input = st.text_input("Deal ID", "DEAL_2024_001")
    uploaded_file = st.file_uploader("Upload deal_spec.json", type=["json"])
    collateral_file = st.file_uploader("Upload initial collateral.json", type=["json"])
    
    # Default JSON template
    default_json = {
        "meta": {"deal_id": deal_id_input}, 
        "collateral": {"original_balance": 10000000},
        "funds": [{"id": "IAF", "description": "Interest"}],
        "bonds": [{"id": "A", "type": "NOTE", "original_balance": 10000000, "priority": {"interest":1, "principal":1}, "coupon": {"kind":"FIXED", "fixed_rate":0.05}}],
        "waterfalls": {"interest": {"steps": []}, "principal": {"steps": []}}
    }

    spec = None
    if uploaded_file is not None:
        try:
            spec = json.load(uploaded_file)
            if "meta" not in spec:
                spec["meta"] = {}
            if "deal_id" not in spec["meta"]:
                spec["meta"]["deal_id"] = deal_id_input
            st.info(f"Loaded deal ID: {spec['meta']['deal_id']}")
            st.caption(f"Uploaded file: {uploaded_file.name}")
        except Exception as e:
            st.error(f"Failed to read uploaded JSON: {e}")

    json_input = st.text_area(
        "Deal JSON Specification",
        json.dumps(spec if spec is not None else default_json, indent=2),
        height=400
    )
    
    if st.button("Upload Deal"):
        try:
            spec = json.loads(json_input)
            if "meta" not in spec:
                spec["meta"] = {}
            deal_id = spec["meta"].get("deal_id") or deal_id_input
            spec["meta"]["deal_id"] = deal_id
            res = requests.post(f"{API_URL}/deals", json={"deal_id": deal_id, "spec": spec}, timeout=10)
            if res.status_code == 200:
                st.success(f"Deal {deal_id} Published Successfully!")
                st.session_state["last_deal_id"] = deal_id
            else:
                st.error(f"Error: {res.text}")
        except RequestException as e:
            st.error(f"API not reachable: {e}")
        except Exception as e:
            st.error(f"Invalid JSON: {e}")

    collateral_deal_id = st.session_state.get("last_deal_id", deal_id_input)
    st.caption(f"Collateral will be stored for deal_id: {collateral_deal_id}")
    if collateral_file is not None:
        if st.button("Upload Collateral"):
            try:
                collateral = json.load(collateral_file)
                res = requests.post(
                    f"{API_URL}/collateral",
                    json={"deal_id": collateral_deal_id, "collateral": collateral},
                    timeout=10
                )
                if res.status_code == 200:
                    st.success(f"Collateral for {collateral_deal_id} stored.")
                else:
                    st.error(f"Error: {res.text}")
            except RequestException as e:
                st.error(f"API not reachable: {e}")
            except Exception as e:
                st.error(f"Invalid JSON: {e}")

    st.subheader("Uploaded Deals")
    st.button("Refresh Deal List")
    deals = fetch_deals()
    if deals:
        st.dataframe(pd.DataFrame(deals))
    else:
        st.info("No deals available yet.")

elif persona == "Servicer (Operations)":
    st.header("Servicer Performance Upload")
    deals = fetch_deals()
    deal_ids = [d.get("deal_id", "") for d in deals if d.get("deal_id")]
    deal_id = st.selectbox("Select Deal", deal_ids) if deal_ids else st.text_input("Deal ID")
    perf_file = st.file_uploader("Upload monthly performance CSV", type=["csv"])
    st.caption("CSV must include Period. Loan-level recommended: LoanId, InterestCollected, PrincipalCollected, Prepayment, RealizedLoss, EndBalance.")

    if perf_file is not None and st.button("Upload Performance"):
        try:
            files = {"file": (perf_file.name, perf_file.getvalue())}
            res = requests.post(f"{API_URL}/performance/{deal_id}", files=files, timeout=30)
            if res.status_code == 200:
                st.success(res.json().get("message", "Performance stored."))
                st.info(f"Latest period: {res.json().get('latest_period')}")
            else:
                st.error(f"Error: {res.text}")
        except RequestException as e:
            st.error(f"API not reachable: {e}")

    if st.button("Clear Performance Data"):
        try:
            res = requests.delete(f"{API_URL}/performance/{deal_id}", timeout=10)
            if res.status_code == 200:
                st.success(res.json().get("message", "Performance cleared."))
            else:
                st.error(f"Error: {res.text}")
        except RequestException as e:
            st.error(f"API not reachable: {e}")

elif persona == "Investor (Analytics)":
    st.header("Risk & Valuation Dashboard")
    
    col1, col2 = st.columns(2)
    with col1:
        deals = fetch_deals()
        deal_ids = [d.get("deal_id", "") for d in deals if d.get("deal_id")]
        st.button("Refresh Deal List", key="refresh_deals_investor")
        selected_deal = None
        if deal_ids:
            selected_deal = st.selectbox("Available Deals", deal_ids)
        deal_id = st.text_input("Load Deal ID", selected_deal or "DEAL_2024_001")
        if deals:
            status_df = pd.DataFrame(deals)
            st.dataframe(status_df)
            if selected_deal:
                row = next((d for d in deals if d.get("deal_id") == selected_deal), None)
                if row and not row.get("has_collateral"):
                    st.warning("Selected deal is missing collateral. Upload collateral before simulation.")
    
    with col2:
        st.subheader("Assumptions")
        cpr = st.slider("CPR (Prepayment)", 0.0, 0.50, 0.10)
        cdr = st.slider("CDR (Default)", 0.0, 0.20, 0.01)
        sev = st.slider("Severity", 0.0, 1.0, 0.40)
        st.subheader("ML Models")
        use_ml = st.checkbox("Use ML Prepay/Default Models", value=False)
        registry = fetch_model_registry()
        model_keys = sorted(registry.keys()) if registry else ["prepay", "default"]
        prepay_model_key = st.selectbox("Prepay Model Key", model_keys, index=0)
        default_model_key = st.selectbox("Default Model Key", model_keys, index=min(1, len(model_keys) - 1))
        rate_scenario = st.selectbox("Rate Scenario", ["rally", "selloff", "base"], index=0)
        start_rate = st.number_input("Start Rate", min_value=0.0, max_value=0.20, value=0.045, step=0.001)
        rate_sensitivity = st.number_input("Rate Sensitivity", min_value=0.0, max_value=5.0, value=1.0, step=0.1)
        feature_source = st.selectbox("ML Feature Source", ["simulated", "market_rates"], index=0)
        origination_source_uri = st.text_input(
            "Origination Tape Path (optional)",
            placeholder="e.g. /path/to/combined_sampled_mortgages_2017_2020.csv",
        )
        
    if st.button("Run Simulation"):
        with st.spinner("Running Cashflow Engine..."):
            try:
                # 1. Start Job
                payload = {
                    "deal_id": deal_id,
                    "cpr": cpr,
                    "cdr": cdr,
                    "severity": sev,
                    "use_ml_models": use_ml,
                    "prepay_model_key": prepay_model_key if use_ml else None,
                    "default_model_key": default_model_key if use_ml else None,
                    "rate_scenario": rate_scenario if use_ml else None,
                    "start_rate": start_rate if use_ml else None,
                    "rate_sensitivity": rate_sensitivity if use_ml else None,
                    "feature_source": feature_source if use_ml else None,
                    "origination_source_uri": origination_source_uri if use_ml and origination_source_uri else None,
                }
                res = requests.post(f"{API_URL}/simulate", json=payload, timeout=10)
            except RequestException as e:
                st.error(f"API not reachable: {e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")
            else:
                if res.status_code == 200:
                    job_id = res.json()['job_id']
                    
                    # 2. Poll for Results (Simplified)
                    import time
                    status = "RUNNING"
                    while status == "RUNNING" or status == "QUEUED":
                        time.sleep(1)
                        try:
                            r2 = requests.get(f"{API_URL}/results/{job_id}", timeout=10)
                        except RequestException as e:
                            st.error(f"API not reachable: {e}")
                            r2 = None
                            break
                        if r2.status_code != 200:
                            st.error(f"API Error: {r2.status_code} {r2.text}")
                            r2 = None
                            break
                        try:
                            payload = r2.json()
                        except ValueError:
                            st.error("API returned non-JSON response from /results.")
                            r2 = None
                            break
                        status = payload.get("status")
                    
                    if r2 is not None and status == "COMPLETED":
                        data = payload.get("data", [])
                        df = pd.DataFrame(data)
                        recon = payload.get("reconciliation", [])
                        actuals_data = payload.get("actuals_data", [])
                        actuals_summary = payload.get("actuals_summary", [])
                        simulated_summary = payload.get("simulated_summary", [])
                        last_actual_period = payload.get("last_actual_period")
                        warnings = payload.get("warnings", [])
                        st.session_state["last_run"] = {
                            "deal_id": deal_id,
                            "simulated_summary": simulated_summary,
                            "ml_status": None,
                        }
                        
                        st.success("Simulation Complete")
                        
                        if warnings:
                            st.subheader("Data Quality Warnings")
                            for warning in warnings:
                                st.warning(warning.get("message", "Warning detected."))
                                sample_rows = warning.get("sample_rows")
                                if sample_rows:
                                    st.dataframe(pd.DataFrame(sample_rows))

                        model_info = payload.get("model_info")
                        if model_info:
                            st.subheader("Model Info")
                            st.dataframe(pd.DataFrame([model_info]))

                        tabs = st.tabs(["Actuals (Servicer Tape)", "Simulated Projection", "Full Detail"])

                        with tabs[0]:
                            if actuals_data:
                                st.caption(f"Actuals loaded through period {last_actual_period}.")
                                st.dataframe(pd.DataFrame(actuals_data))
                            else:
                                st.info("No actuals data available from performance uploads.")
                            if actuals_summary:
                                st.subheader("Servicer Aggregate Summary")
                                st.dataframe(pd.DataFrame(actuals_summary))

                        with tabs[1]:
                            if last_actual_period is not None:
                                sim_df = df[df["Period"] > last_actual_period]
                            else:
                                sim_df = df
                            st.subheader("Cashflow Waterfall (Simulated)")
                            bond_cols = [c for c in sim_df.columns if "Bond." in c and ".Balance" in c]
                            if not sim_df.empty and bond_cols:
                                st.line_chart(sim_df.set_index("Period")[bond_cols])
                            else:
                                st.info("No simulated periods available.")
                            if simulated_summary:
                                st.subheader("Simulated Aggregate Summary")
                                st.dataframe(pd.DataFrame(simulated_summary))
                            ml_cols = [
                                "Var.MLUsed",
                                "Var.ModelSource",
                                "Var.MLPoolCount",
                                "Var.MLPoolBalance",
                                "Var.MLSourceURI",
                                "Var.MLFeatureSource",
                                "Var.MLPrepayStrategy",
                                "Var.MLDefaultStrategy",
                                "Var.MLRateScenario",
                                "Var.MLStartRate",
                                "Var.MLRateFirst",
                                "Var.MLRateMean",
                                "Var.MLRateSensitivity",
                            ]
                            if not sim_df.empty and any(c in sim_df.columns for c in ml_cols):
                                last_sim = sim_df.iloc[-1]
                                ml_status = {c.replace("Var.", ""): last_sim.get(c) for c in ml_cols if c in sim_df.columns}
                                if ml_status:
                                    st.subheader("ML Status (Latest Sim Period)")
                                    extra_cols = ["RateMean", "RateIncentiveMean", "BurnoutMean", "CPR"]
                                    for col in extra_cols:
                                        if col in sim_df.columns:
                                            ml_status[col] = last_sim.get(col)
                                    ml_status_df = pd.DataFrame([ml_status])
                                    st.dataframe(ml_status_df)
                                    st.download_button(
                                        "Download ML Status CSV",
                                        ml_status_df.to_csv(index=False),
                                        "ml_status_simulated.csv"
                                    )
                                    st.session_state["last_run"]["ml_status"] = ml_status
                            st.dataframe(sim_df)
                            if actuals_summary:
                                st.subheader("Servicer Aggregate Summary")
                                st.dataframe(pd.DataFrame(actuals_summary))

                        with tabs[2]:
                            st.subheader("Detailed Tape (Full)")
                            st.dataframe(df)
                            st.download_button("Download CSV", df.to_csv(index=False), "results.csv")
                            if simulated_summary:
                                st.subheader("Simulated Aggregate Summary")
                                st.dataframe(pd.DataFrame(simulated_summary))
                            if not df.empty and any(c in df.columns for c in ml_cols):
                                last_full = df.iloc[-1]
                                ml_status_full = {c.replace("Var.", ""): last_full.get(c) for c in ml_cols if c in df.columns}
                                if ml_status_full:
                                    st.subheader("ML Status (Latest Period)")
                                    ml_status_full_df = pd.DataFrame([ml_status_full])
                                    st.dataframe(ml_status_full_df)
                                    st.download_button(
                                        "Download ML Status CSV",
                                        ml_status_full_df.to_csv(index=False),
                                        "ml_status_full.csv"
                                    )
                            if actuals_summary:
                                st.subheader("Servicer Aggregate Summary")
                                st.dataframe(pd.DataFrame(actuals_summary))

                        if recon:
                            st.subheader("Servicer Reconciliation")
                            st.dataframe(pd.DataFrame(recon))
                        else:
                            st.info("No reconciliation issues detected.")
                        last_run = st.session_state.get("last_run_prev")
                        curr_run = st.session_state.get("last_run")
                        if last_run and curr_run and last_run.get("deal_id") == curr_run.get("deal_id"):
                            st.subheader("Run Comparison (Latest vs Previous)")
                            left = pd.DataFrame([last_run.get("ml_status", {})])
                            right = pd.DataFrame([curr_run.get("ml_status", {})])
                            if not left.empty and not right.empty:
                                left["Run"] = "Previous"
                                right["Run"] = "Latest"
                                compare_df = pd.concat([left, right], ignore_index=True)
                                st.dataframe(compare_df)
                            prev_summary = pd.DataFrame(last_run.get("simulated_summary", []) or [])
                            curr_summary = pd.DataFrame(curr_run.get("simulated_summary", []) or [])
                            if not prev_summary.empty and not curr_summary.empty and "Period" in prev_summary.columns and "Period" in curr_summary.columns:
                                merged = prev_summary.merge(curr_summary, on="Period", suffixes=("_prev", "_latest"))
                                diff_cols = []
                                for col in prev_summary.columns:
                                    if col == "Period":
                                        continue
                                    prev_col = f"{col}_prev"
                                    latest_col = f"{col}_latest"
                                    if prev_col in merged.columns and latest_col in merged.columns:
                                        merged[f"{col}_delta"] = merged[latest_col] - merged[prev_col]
                                        diff_cols.append(f"{col}_delta")
                                if diff_cols:
                                    st.subheader("Simulated Summary Deltas")
                                    st.dataframe(merged[["Period"] + diff_cols])
                        st.session_state["last_run_prev"] = st.session_state.get("last_run")
                    else:
                        err = payload.get("error") if r2 is not None else None
                        st.error(f"Simulation Failed{': ' + err if err else ''}")
                else:
                    st.error(f"API Error: {res.text}")