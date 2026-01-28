import streamlit as st
import pandas as pd
import math
from io import BytesIO

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="PTL IM Generator",
    layout="wide"
)

st.title("📦 PTL Internal Movement (IM) Generator")
st.caption("Demand-driven | Batch-aware | Pick-face optimized")

# --------------------------------------------------
# FILE UPLOADS
# --------------------------------------------------
st.sidebar.header("📂 Upload Files")

ptl_file = st.sidebar.file_uploader("PTL Demand File", type="xlsx")
sap_file = st.sidebar.file_uploader("SAP Inventory File", type="xlsx")
wms_file = st.sidebar.file_uploader("WMS Inventory File", type="xlsx")
sku_file = st.sidebar.file_uploader("SKU–Bin Mapping File", type="xlsx")

run_analysis = st.sidebar.button("🔍 Run Analysis")
generate_im = st.sidebar.button("🚚 Generate IM File")

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
if "decision" not in st.session_state:
    st.session_state.decision = None
if "im_df" not in st.session_state:
    st.session_state.im_df = None

# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------
if run_analysis and all([ptl_file, sap_file, wms_file, sku_file]):

    # ---------- PTL DEMAND ----------
    ptl = pd.read_excel(ptl_file)

    ptl["Required_Zones"] = ptl["Lines"].apply(lambda x: math.ceil(x / 60))

    # ---------- SAP INVENTORY ----------
    sap = pd.read_excel(sap_file, sheet_name="batch mapping")
    qty_col = sap.columns[16]  # Column Q

    sap = sap.rename(columns={
        "product": "Product",
        "sku": "SKU",
        "batch": "Batch",
        "type": "Type",
        qty_col: "Available_Qty"
    })

    sap["Priority"] = sap["Type"].map({"ATP_PICK": 0, "ATP_RESERVE": 1})
    sap = sap.sort_values(["Product", "Priority", "expiryDate"])

    # ---------- WMS INVENTORY ----------
    wms = pd.read_excel(
        wms_file,
        sheet_name="HU Level",
        usecols="C,D,E,F,M,N,Q,Y"
    )

    wms.columns = [
        "Area", "Zone", "Bin", "BinType",
        "Product", "SKU", "Batch", "Qty"
    ]

    wms = wms[
        (wms["Area"] == "PTL") &
        (wms["Zone"] <= 8) &
        (wms["BinType"] != "PTL3")
    ]

    # ---------- SKU MASTER ----------
    sku_map = pd.read_excel(sku_file, usecols=[0, 2])
    sku_map.columns = ["Bin", "Product"]

    # ---------- WMS STATE ----------
    wms_bins = (
        wms.groupby(["Product", "SKU", "Batch", "Bin"])
        .agg(Qty=("Qty", "sum"))
        .reset_index()
    )

    wms_summary = (
        wms_bins.groupby(["Product", "SKU", "Batch"])
        .agg(
            WMS_Bin_Count=("Bin", "nunique"),
            WMS_Total_Qty=("Qty", "sum")
        )
        .reset_index()
    )

    # ---------- DECISION TABLE ----------
    decision = ptl.merge(
        wms_summary,
        left_on=["Product Code", "Sku-batch"],
        right_on=["Product", "SKU"],
        how="left"
    ).fillna(0)

    actions = []
    error_flags = []
    error_reasons = []

    for _, r in decision.iterrows():
        action = "NO ACTION"
        error = ""

        if r["WMS_Bin_Count"] > r["Required_Zones"]:
            action = "CONSOLIDATE"

        elif r["WMS_Bin_Count"] < r["Required_Zones"]:
            action = "DISTRIBUTE"

            allowed_bins = sku_map[sku_map["Product"] == r["Product Code"]]["Bin"]
            used_bins = wms_bins[
                (wms_bins["Product"] == r["Product Code"]) &
                (wms_bins["Batch"] == r["Batch"])
            ]["Bin"]

            empty_bins = set(allowed_bins) - set(used_bins)
            if len(empty_bins) == 0:
                error = "No empty bins available"

        actions.append(action)
        error_reasons.append(error)
        error_flags.append("YES" if error else "NO")

    decision["Action"] = actions
    decision["Error_Flag"] = error_flags
    decision["Error_Reason"] = error_reasons

    st.session_state.decision = decision

# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------
if st.session_state.decision is not None:

    d = st.session_state.decision

    st.subheader("📊 Dashboard")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total SKU–Batches", len(d))
    c2.metric("Consolidations", (d.Action == "CONSOLIDATE").sum())
    c3.metric("Distributions", (d.Action == "DISTRIBUTE").sum())
    c4.metric("Errors", (d.Error_Flag == "YES").sum())

    st.subheader("📋 SKU–Batch Decision Table")
    st.dataframe(d, use_container_width=True)

    if (d.Error_Flag == "YES").any():
        st.subheader("⚠️ Error Records (IM will not be generated for these)")
        st.dataframe(d[d.Error_Flag == "YES"])

# --------------------------------------------------
# IM GENERATION
# --------------------------------------------------
if generate_im and st.session_state.decision is not None:

    decision = st.session_state.decision
    im_rows = []

    # ---------- CONSOLIDATION FIRST ----------
    for _, r in decision.iterrows():
        if r["Action"] == "CONSOLIDATE" and r["Error_Flag"] == "NO":

            bins = wms_bins[
                (wms_bins["Product"] == r["Product Code"]) &
                (wms_bins["SKU"] == r["Sku-batch"]) &
                (wms_bins["Batch"] == r["Batch"])
            ].sort_values("Qty")

            excess = int(r["WMS_Bin_Count"] - r["Required_Zones"])
            if excess <= 0 or bins.empty:
                continue

            target_bin = bins.iloc[-1]["Bin"]

            for i in range(excess):
                src = bins.iloc[i]
                im_rows.append([
                    src["Bin"], "",
                    r["Sku-batch"], r["Batch"],
                    "Good", "L0",
                    src["Qty"], target_bin, ""
                ])

    # ---------- DISTRIBUTION NEXT ----------
    for _, r in decision.iterrows():
        if r["Action"] == "DISTRIBUTE" and r["Error_Flag"] == "NO":

            needed = int(r["Required_Zones"] - r["WMS_Bin_Count"])
            if needed <= 0:
                continue

            allowed_bins = sku_map[sku_map["Product"] == r["Product Code"]]["Bin"]
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
            per_bin_qty = max(1, int(r["Quantity"] / needed))

            for b in empty_bins[:needed]:
                im_rows.append([
                    src["Bin"], "",
                    r["Sku-batch"], r["Batch"],
                    "Good", "L0",
                    per_bin_qty, b, ""
                ])

    im_df = pd.DataFrame(im_rows, columns=[
        "Source Bin",
        "HU Code",
        "SKU",
        "Batch",
        "Quality",
        "UOM",
        "Quantity",
        "Destination Bin",
        "Pick HU"
    ])

    st.session_state.im_df = im_df

# --------------------------------------------------
# DOWNLOAD
# --------------------------------------------------
if st.session_state.im_df is not None:

    st.subheader("⬇️ Download IM File")

    output = BytesIO()
    st.session_state.im_df.to_excel(output, index=False)
    output.seek(0)

    st.download_button(
        label="Download IM Excel",
        data=output,
        file_name="IM_Final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
