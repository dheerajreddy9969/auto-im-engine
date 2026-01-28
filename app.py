import streamlit as st
import pandas as pd
import math
from io import BytesIO

# ==================================================
# PAGE CONFIG
# ==================================================
st.set_page_config(page_title="PTL IM Engine", layout="wide")
st.title("📦 PTL Internal Movement (IM) Engine")
st.caption("Priority-driven | Batch-safe | Space-aware")

# ==================================================
# LOADERS
# ==================================================

def load_ptl_demand(file):
    df = pd.read_excel(file)
    df["Required_Zones"] = df["Lines"].apply(lambda x: math.ceil(x / 60))
    return df


def load_sap_inventory(file):
    sap = pd.read_excel(file, sheet_name="batch mapping")
    qty_col = sap.columns[16]

    sap = sap.rename(columns={
        "product": "Product",
        "sku": "SKU",
        "batch": "Batch",
        "type": "ATP_Type",
        qty_col: "Available_Qty"
    })

    sap["Alloc_Priority"] = sap["ATP_Type"].map({
        "ATP_PICK": 1,
        "ATP_RESERVE": 0
    })

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

    wms["Zone"] = pd.to_numeric(wms["Zone"], errors="coerce")
    wms = wms.dropna(subset=["Zone"])
    wms["Zone"] = wms["Zone"].astype(int)

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
# STATE BUILDERS
# ==================================================

def build_wms_state(wms):
    bins = (
        wms.groupby(["Product", "SKU", "Batch", "Bin"], as_index=False)
        .agg(Qty=("Qty", "sum"))
    )

    summary = (
        bins.groupby(["Product", "Batch"], as_index=False)
        .agg(
            Bin_Count=("Bin", "nunique"),
            Total_Qty=("Qty", "sum")
        )
    )

    return bins, summary


# ==================================================
# CORE DECISION ENGINE
# ==================================================

def build_decision(ptl, sap, wms_summary):
    decision = ptl.merge(
        wms_summary,
        left_on="Product Code",
        right_on="Product",
        how="inner"
    )

    decision = decision.merge(
        sap[["Product", "Batch", "Alloc_Priority"]],
        on=["Product", "Batch"],
        how="left"
    ).fillna({"Alloc_Priority": 0})

    decision["Status"] = "NO ACTION"

    return decision


# ==================================================
# IM GENERATION HELPERS
# ==================================================

def consolidate_batch(batch_row, wms_bins):
    moves = []
    bins = wms_bins[
        (wms_bins["Product"] == batch_row["Product"]) &
        (wms_bins["Batch"] == batch_row["Batch"])
    ].sort_values("Qty")

    if len(bins) <= 1:
        return moves, []

    target = bins.iloc[-1]["Bin"]
    freed_bins = []

    for i in range(len(bins) - 1):
        src = bins.iloc[i]
        moves.append([
            src["Bin"], "",
            src["SKU"], src["Batch"],
            "Good", "L0",
            src["Qty"], target, ""
        ])
        freed_bins.append(src["Bin"])

    return moves, freed_bins


def distribute_batch(batch_row, wms_bins, empty_bins):
    moves = []

    src = wms_bins[
        (wms_bins["Product"] == batch_row["Product"]) &
        (wms_bins["Batch"] == batch_row["Batch"])
    ].sort_values("Qty", ascending=False).iloc[0]

    per_bin_qty = max(1, int(src["Qty"] / len(empty_bins)))

    for b in empty_bins:
        moves.append([
            src["Bin"], "",
            src["SKU"], src["Batch"],
            "Good", "L0",
            per_bin_qty, b, ""
        ])

    return moves


# ==================================================
# MAIN ENGINE
# ==================================================

def generate_ims(decision, wms_bins, sku_map):
    ims = []
    diagnostics = []

    for sku, sku_df in decision.groupby("Product Code"):

        allowed_bins = set(
            sku_map[sku_map["Product"] == sku]["Bin"]
        )

        used_bins = set(
            wms_bins[wms_bins["Product"] == sku]["Bin"]
        )

        empty_bins = list(allowed_bins - used_bins)

        target_batches = sku_df[
            sku_df["Alloc_Priority"] == 1
        ].sort_values("Required_Zones", ascending=False)

        for _, target in target_batches.iterrows():

            if target["Bin_Count"] >= target["Required_Zones"]:
                diagnostics.append((sku, target["Batch"], "Already sufficient"))
                continue

            if empty_bins:
                ims += distribute_batch(target, wms_bins, empty_bins[:1])
                diagnostics.append((sku, target["Batch"], "Used empty bin"))
                continue

            # Priority 1: over-spread batches
            candidates = sku_df[
                (sku_df["Batch"] != target["Batch"]) &
                (sku_df["Bin_Count"] > sku_df["Required_Zones"])
            ]

            freed = False
            for _, c in candidates.iterrows():
                cons, freed_bins = consolidate_batch(c, wms_bins)
                if freed_bins:
                    ims += cons
                    ims += distribute_batch(target, wms_bins, freed_bins[:1])
                    diagnostics.append((sku, target["Batch"], f"Freed from {c['Batch']}"))
                    freed = True
                    break

            if freed:
                continue

            # Priority 2: non-allocating batches
            fallback = sku_df[
                (sku_df["Batch"] != target["Batch"]) &
                (sku_df["Alloc_Priority"] == 0) &
                (sku_df["Bin_Count"] > 1)
            ]

            for _, c in fallback.iterrows():
                cons, freed_bins = consolidate_batch(c, wms_bins)
                if freed_bins:
                    ims += cons
                    ims += distribute_batch(target, wms_bins, freed_bins[:1])
                    diagnostics.append((sku, target["Batch"], f"Freed from non-alloc {c['Batch']}"))
                    freed = True
                    break

            if not freed:
                diagnostics.append((sku, target["Batch"], "MANUAL INTERVENTION"))

    return ims, diagnostics


# ==================================================
# STREAMLIT UI
# ==================================================

st.sidebar.header("📂 Upload Files")

ptl_file = st.sidebar.file_uploader("PTL Demand File", type="xlsx")
sap_file = st.sidebar.file_uploader("SAP Inventory File", type="xlsx")
wms_file = st.sidebar.file_uploader("WMS Inventory File", type="xlsx")
sku_file = st.sidebar.file_uploader("SKU–Bin Mapping File", type="xlsx")

run = st.sidebar.button("▶ Run Engine")

if run and all([ptl_file, sap_file, wms_file, sku_file]):

    ptl = load_ptl_demand(ptl_file)
    sap = load_sap_inventory(sap_file)
    wms = load_wms_inventory(wms_file)
    sku_map = load_sku_master(sku_file)

    wms_bins, wms_summary = build_wms_state(wms)
    decision = build_decision(ptl, sap, wms_summary)

    ims, diag = generate_ims(decision, wms_bins, sku_map)

    im_df = pd.DataFrame(ims, columns=[
        "Source Bin", "HU Code", "SKU", "Batch",
        "Quality", "UOM", "Quantity",
        "Destination Bin", "Pick HU"
    ])

    diag_df = pd.DataFrame(diag, columns=["Product", "Batch", "Outcome"])

    st.subheader("📊 Diagnostics")
    st.dataframe(diag_df, use_container_width=True)

    st.subheader("📄 Generated IMs")
    st.success(f"Total IM rows generated: {len(im_df)}")
    st.dataframe(im_df, use_container_width=True)

    out = BytesIO()
    im_df.to_excel(out, index=False)
    out.seek(0)

    st.download_button(
        "⬇ Download IM File",
        data=out,
        file_name="IM_Final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
