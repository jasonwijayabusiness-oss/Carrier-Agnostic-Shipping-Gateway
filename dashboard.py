import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from app.db import init_db, get_conn, DB_PATH

API = "http://127.0.0.1:8000"
st.set_page_config(page_title="Carrier Platform V3", layout="wide")

def query_df(sql: str, params=()):
    conn = get_conn()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()

def post(path: str, payload=None):
    payload = payload or {}
    r = requests.post(f"{API}{path}", json=payload, timeout=20)
    try:
        return r.json()
    except Exception:
        return {"raw": r.text}

def get(path: str):
    return requests.get(f"{API}{path}", timeout=20).json()

init_db()
st.title("Carrier-Agnostic Shipping Platform (V3)")
st.caption(f"SQLite DB: {DB_PATH}")

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    if st.button("Seed 40 orders"):
        st.write(post("/orders/seed", {"n": 40}))
with c2:
    if st.button("Refresh"):
        st.rerun()
with c3:
    if st.button("Trigger Sendle shutdown"):
        st.write(post("/mock/sendle/toggle_shutdown", {"shutdown": True}))
with c4:
    if st.button("Recover Sendle mock"):
        st.write(post("/mock/sendle/toggle_shutdown", {"shutdown": False}))
with c5:
    if st.button("Run release gate"):
        st.write(post("/ops/release_gate_run", {}))
with c6:
    if st.button("Enable SENDLE provider"):
        st.write(post("/providers/SENDLE/enable", {}))

st.divider()
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Orders", "Quotes & Routing", "Shipments", "Carriers", "Incidents", "SQL Console"])

with tab1:
    orders = pd.DataFrame(get("/orders?limit=200")["orders"])
    st.dataframe(orders.sort_values("order_id") if not orders.empty else orders, use_container_width=True)

with tab2:
    order_id = st.text_input("Order ID", value="ORDER-0001")
    if st.button("Generate quotes for this order"):
        quotes = pd.DataFrame(get(f"/quotes/{order_id}")["quotes"])
        st.dataframe(quotes, use_container_width=True)
    if st.button("Create label for this order"):
        st.write(post("/shipments/create_label", {"order_id": order_id}))

    st.subheader("Promise risk count")
    st.dataframe(query_df("SELECT COUNT(*) AS promise_risk_cnt FROM shipments WHERE selection_reason LIKE '%PROMISE_RISK%';"), use_container_width=True)

with tab3:
    ship = pd.DataFrame(get("/shipments?limit=200")["shipments"])
    st.dataframe(ship, use_container_width=True)

    att = query_df("SELECT created_at, order_id, provider, success, error_code FROM label_attempts ORDER BY created_at DESC LIMIT 300;")
    st.subheader("Label attempts (audit trail)")
    st.dataframe(att, use_container_width=True)

    if not att.empty:
        att["created_at"] = pd.to_datetime(att["created_at"])
        att["minute"] = att["created_at"].dt.floor("min")
        grp = att.groupby(["minute","provider"]).agg(attempts=("success","count"), successes=("success","sum")).reset_index()
        grp["success_rate"] = grp["successes"]/grp["attempts"]
        fig = plt.figure()
        for p in grp["provider"].unique():
            sub = grp[grp["provider"]==p]
            plt.plot(sub["minute"], sub["success_rate"], label=p)
        plt.ylim(0, 1.05)
        plt.title("Label success rate over time")
        plt.xlabel("Time")
        plt.ylabel("Success rate")
        plt.legend()
        st.pyplot(fig)

with tab4:
    carriers = pd.DataFrame(get("/carriers")["carriers"])
    st.dataframe(carriers, use_container_width=True)
    prov = st.selectbox("Toggle carrier", ["SENDLE","ALT","AUSPOST"])
    enabled = st.checkbox("Enabled", value=True)
    if st.button("Apply carrier toggle"):
        st.write(post(f"/carriers/{prov}/toggle?enabled={'true' if enabled else 'false'}", {}))
    st.subheader("Provider kill switch status")
    st.dataframe(pd.DataFrame(get("/providers")["providers"]), use_container_width=True)

with tab5:
    inc = pd.DataFrame(get("/incidents?limit=200")["incidents"])
    st.dataframe(inc, use_container_width=True)

with tab6:
    default_sql = """-- Latest quotes
SELECT order_id, provider, lane_type, quoted_cost, estimated_days, eligible, ineligible_reason, created_at
FROM rate_quotes
ORDER BY created_at DESC
LIMIT 30;"""
    sql = st.text_area("SQL", value=default_sql, height=220)
    if st.button("Run SQL"):
        try:
            st.dataframe(query_df(sql), use_container_width=True)
        except Exception as e:
            st.error(str(e))
