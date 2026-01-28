import streamlit as st
import pandas as pd
import math
from io import BytesIO

# ==================================================
# PAGE CONFIG
# ==================================================
st.set_page_config(page_title="PTL IM Engine", layout="wide")
st.title("📦 PTL Internal Movement (IM) Engine")
st.caption("SAP-aware | WMS-driven | Consolidation → Balancing")

# ==================================================
# LOADERS
# ==================================================

def load_ptl_demand(file):
    df = pd.read_excel(file)
    df["Required_Zones"] = df["Lines"].apply(lambda x: math.ceil(x / 60))
    return df


def load_sap_inventory(file):
    """
    SAP inventory is NOT directly used for IM execution yet,
    but is loaded, validated, and kept ready for:
    - batch prioritisation
    - future allocation logic
    """
    sap = pd.read_excel(file, sheet_name="batch mapping")

    qty_col = sap.columns[16]  # Column Q as per your rule

    sap = sap.rename(columns={
        "product": "Product",
        "sku": "SKU",
        "batch": "Batch",
        "type": "ATP_Type",
        qty_col: "Available_Qty"
    })

    sap["ATP_Priority"] = sap["ATP_Type"].map({
        "ATP_PICK": 0,
        "ATP_RESERVE": 1
    })

    sap = sap.sort_values(
        ["Product", "ATP_Priority", "expiryDate"],
        ascending=[True, True, True]
    )

    return sap


def load_wms_inventory(file):
    wms = pd.read_excel(
        file,
        sheet_name="HU Level",
        usecols="C,D,E,F,M,N,Q,Y"
    )

    wms.columns = [
        "Area", "Zone", "Bin", "BinType",
        "Product", "SKU", "Batch", "Qty"
    ]

    # ---- FIX: Zone must be numeric ----
    wms["Zone"] = pd.to_numeric(wms["Zone"], errors="coerce")
    wms = wms.dropna(subset=["Zone"])
    wms["Zone"] = wms["Zone"].astype(int)

    # ---- Business filters ----
    wms = wms[
        (wms["Area"] == "PTL") &
        (wms["Zone"] <= 8) &
        (wms["BinType"] != "PTL3")
    ]

    return wms


def load_sku_master(file):
    sku = pd.read_excel(file, usecols=[0, 2])
    sku.columns = ["Bin", "Product"]
    return sku


# ==================================================
# CORE STATE BUILD
# ==================================================

def build_wms_state(wms):
    wms_bins = (
        wms.groupby(["Product", "SKU", "Batch", "Bin"], as_index=False)
        .agg(Qty=("Qty", "sum"))
    )

    wms_summary = (
        wms_bins.groupby(["Product", "Batch"], as_index=False)
        .agg(
            WMS_Bin_Count=("Bin", "nunique"),
            WMS_Total_Qty=("Qty", "sum")
        )
    )

    return wms_bins, wms_summary


def build_decision_table(ptl, wms_summary):
    """
    Decision table is Product–Batch based.
    Required_Zones comes from PTL demand.
    """
    decision = ptl.merge(
        wms_summary,
        left_on="Product Code",
        right_on="Product",
        how="inner"
    )

    decision["Action"] = "NO ACTION"

    decision.loc[
        decision["WMS_Bin_Count"] > decision["Required_Zones"],
        "Action"
    ] = "CONSOLIDATE"

    decision.loc[
        decision["WMS_Bin_Count"] < decision["Required_Zones"],
        "Action"
    ] = "DISTRIBUTE"

    return decision


# ==================================================
# ERROR DETECTION
# ==================================================

def detect_errors(decision, wms_bins, sku_map):
    error_reason = []

    for _, r in decision.iterrows():
        error = ""

        if r["Action"] == "DISTRIBUTE":
            allowed_bins = sku_map[
                sku_map["Product"] == r["Product Code"]
            ]["Bin"]

            used_bins = wms_bins[
                (wms_bins["Product"] == r["Product Code"]) &
                (wms_bins["Batch"] == r["Batch"])
            ]["Bin"]

            if len(set(allowed_bins) - set(used_bins)) == 0:
                error = "No empty bins available"

        error_reason.append(error)

    decision["Error_Reason"] = error_reason
    decision["Error_Flag"] = decision["Error_Reason"].apply(
        lambda x: "YES" if x else "NO"
    )

    return decision


# ==================================================
# IM GENERATION
# ==================================================

def generate_consolidation_ims(decision, wms_bins):
    rows = []

    for _, r in decision.iterrows():
        if r["Action"] != "CONSOLIDATE" or r["Error_Flag"] == "YES":
            continue

        bins = wms_bins[
            (wms_bins["Product"] == r["Product Code"]) &
            (wms_bins["Batch"] == r["Batch"])
        ].sort_values("Qty")

        excess = int(r["WMS_Bin_Count"] - r["Required_Zones"])
        if excess <= 0 or bins.empty:
            continue

        target = bins.iloc[-1]

        for i in range(excess):
            src = bins.iloc[i]
            rows.append([
                src["Bin"], "",
                src["SKU"], r["Batch"],
                "Good", "L0",
                src["Qty"],
                target["Bin"],
                ""
            ])

    return rows


def generate_distribution_ims(decision, wms_bins, sku_map):
    rows = []

    for _, r in decision.iterrows():
        if r["Action"] != "DISTRIBUTE" or r["Error_Flag"] == "YES":
            continue

        needed = int(r["Required_Zones"] - r["WMS_Bin_Count"])
        if needed <= 0:
            continue

        allowed_bins = sku_map[
            sku_map["Product"] == r["Product Code"]
        ]["Bin"]

        used_bins = wms_bins[
            (wms_bins["Product"] == r["Product Code"]) &
            (wms_bins["Batch"] == r["Batch"])
        ]["Bin"]

        empty_bins = list(set(allowed_bins) - set(used_bins))
        if not empty_bins:
            continue

        src_bins = wms_bins[
            (wms_bins["Product"] == r["Product Code"]) &
            (wms_bins["Batch"] == r["Batch"])
        ]

        if src_bins.empty:
            continue

        src = src_bins.sort_values("Qty", ascending=False).iloc[0]
        per_bin_qty = max(1, int(src["Qty"] / needed))

        for b in empty_bins[:needed]:
            rows.append([
                src["Bin"], "",
                src["SKU"], r["Batch"],
                "Good", "L0",
                per_bin_qty,
                b,
                ""
            ])

    return rows


# ==================================================
# STREAMLIT UI
# ==================================================

st.sidebar.header("📂 Upload Files")

ptl_file = st.sidebar.file_uploader("PTL Demand File", type="xlsx")
sap_file = st.sidebar.file_uploader("SAP Inventory File", type="xlsx")
wms_file = st.sidebar.file_uploader("WMS Inventory File", type="xlsx")
sku_file = st.sidebar.file_uploader("SKU–Bin Mapping File", type="xlsx")

run_analysis = st.sidebar.button("🔍 Run Analysis")
generate_im = st.sidebar.button("🚚 Generate IM")

# ==================================================
# RUN ANALYSIS
# ==================================================

if run_analysis and all([ptl_file, sap_file, wms_file, sku_file]):

    ptl = load_ptl_demand(ptl_file)
    sap = load_sap_inventory(sap_file)     # ✅ SAP LOADED
    wms = load_wms_inventory(wms_file)
    sku_map = load_sku_master(sku_file)

    wms_bins, wms_summary = build_wms_state(wms)
    decision = build_decision_table(ptl, wms_summary)
    decision = detect_errors(decision, wms_bins, sku_map)

    # Store in session
    st.session_state.decision = decision
    st.session_state.wms_bins = wms_bins
    st.session_state.sku_map = sku_map
    st.session_state.sap = sap   # kept for future logic

# ==================================================
# DASHBOARD
# ==================================================

if "decision" in st.session_state:

    d = st.session_state.decision

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKU–Batches", len(d))
    c2.metric("Consolidate", (d.Action == "CONSOLIDATE").sum())
    c3.metric("Distribute", (d.Action == "DISTRIBUTE").sum())
    c4.metric("Errors", (d.Error_Flag == "YES").sum())

    st.subheader("📋 Decision Table")
    st.dataframe(d, use_container_width=True)

    if (d.Error_Flag == "YES").any():
        st.subheader("⚠️ Error Records")
        st.dataframe(d[d.Error_Flag == "YES"])

st.subheader("🧪 IM Trigger Diagnostics")

st.write("Consolidation candidates:")
st.write(
    st.session_state.decision[
        st.session_state.decision.WMS_Bin_Count >
        st.session_state.decision.Required_Zones
    ][["Product Code","Batch","WMS_Bin_Count","Required_Zones"]]
)

st.write("Distribution candidates:")
st.write(
    st.session_state.decision[
        st.session_state.decision.WMS_Bin_Count <
        st.session_state.decision.Required_Zones
    ][["Product Code","Batch","WMS_Bin_Count","Required_Zones"]]
)






# ==================================================
# IM FILE GENERATION
# ==================================================

if generate_im and "decision" in st.session_state:

    cons = generate_consolidation_ims(
        st.session_state.decision,
        st.session_state.wms_bins
    )

    dist = generate_distribution_ims(
        st.session_state.decision,
        st.session_state.wms_bins,
        st.session_state.sku_map
    )

    im_df = pd.DataFrame(
        cons + dist,
        columns=[
            "Source Bin",
            "HU Code",
            "SKU",
            "Batch",
            "Quality",
            "UOM",
            "Quantity",
            "Destination Bin",
            "Pick HU"
        ]
    )

    st.success(f"IM rows generated: {len(im_df)}")

    output = BytesIO()
    im_df.to_excel(output, index=False)
    output.seek(0)

    st.download_button(
        "⬇️ Download IM File",
        data=output,
        file_name="IM_Final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
