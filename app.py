import streamlit as st
import pandas as pd
import math
from io import BytesIO

# ==================================================
# PAGE CONFIG
# ==================================================
st.set_page_config(page_title="PTL IM Engine", layout="wide")
st.title("📦 PTL Internal Movement (IM) Engine")
st.caption("PTL-driven | SKU–Batch accurate | Preview before execution")

# ==================================================
# LOADERS
# ==================================================

def load_ptl_demand(file):
    """
    PTL Demand:
    Column B = SKU
    Column C = Batch
    Lines & Quantity are SKU–Batch specific
    """
    df = pd.read_excel(file)

    df = df.rename(columns={
        df.columns[1]: "SKU",      # Column B
        df.columns[2]: "Batch",    # Column C
        df.columns[3]: "Quantity",
        df.columns[4]: "Lines"
    })

    df["Required_Zones"] = df["Lines"].apply(
        lambda x: math.ceil(x / 60)
    )

    return df


def load_sap_inventory(file):
    sap = pd.read_excel(file, sheet_name="batch mapping")
    qty_col = sap.columns[16]

    sap = sap.rename(columns={
        "product": "Product",
        "sku": "SKU",
        "batch": "Batch",
        qty_col: "Available_Qty"
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
        wms.groupby(["SKU", "Batch", "Bin"], as_index=False)
        .agg(Qty=("Qty", "sum"))
    )

    summary = (
        bins.groupby(["SKU", "Batch"], as_index=False)
        .agg(Bin_Count=("Bin", "nunique"))
    )

    return bins, summary


# ==================================================
# IM HELPERS
# ==================================================

def consolidate_batch(batch_row, wms_bins):
    moves = []

    bins = wms_bins[
        (wms_bins["SKU"] == batch_row["SKU"]) &
        (wms_bins["Batch"] == batch_row["Batch"])
    ].sort_values("Qty")

    if len(bins) <= 1:
        return moves, []

    target_bin = bins.iloc[-1]["Bin"]
    freed_bins = []

    for i in range(len(bins) - 1):
        src = bins.iloc[i]
        moves.append([
            src["Bin"], "",
            batch_row["SKU"], batch_row["Batch"],
            "Good", "L0",
            src["Qty"], target_bin, ""
        ])
        freed_bins.append(src["Bin"])

    return moves, freed_bins


def distribute_batch(batch_row, wms_bins, empty_bins):
    moves = []

    src_bins = wms_bins[
        (wms_bins["SKU"] == batch_row["SKU"]) &
        (wms_bins["Batch"] == batch_row["Batch"])
    ]

    # 🔑 FIX: No source bins → cannot distribute
    if src_bins.empty:
        return moves

    src = src_bins.sort_values("Qty", ascending=False).iloc[0]

    per_bin_qty = max(
        1, int(batch_row["Quantity"] / len(empty_bins))
    )

    for b in empty_bins:
        moves.append([
            src["Bin"], "",
            batch_row["SKU"], batch_row["Batch"],
            "Good", "L0",
            per_bin_qty, b, ""
        ])

    return moves



# ==================================================
# MAIN ENGINE
# ==================================================

def generate_ims(ptl, wms_bins, wms_summary, sku_map):
    ims = []
    diagnostics = []

    for _, row in ptl.iterrows():

        sku = row["SKU"]
        batch = row["Batch"]
        required = row["Required_Zones"]

        current = wms_summary[
            (wms_summary["SKU"] == sku) &
            (wms_summary["Batch"] == batch)
        ]

        bin_count = int(current["Bin_Count"].iloc[0]) if not current.empty else 0

        # Find empty bins
        allowed_bins = set(
            sku_map["Bin"]
        )
        used_bins = set(
            wms_bins[
                (wms_bins["SKU"] == sku) &
                (wms_bins["Batch"] == batch)
            ]["Bin"]
        )

        empty_bins = list(allowed_bins - used_bins)

        if bin_count >= required:
            diagnostics.append((sku, batch, "NO ACTION – sufficient bins"))
            continue

        if empty_bins:
            ims += distribute_batch(row, wms_bins, empty_bins[:1])
            diagnostics.append((sku, batch, "DISTRIBUTED using empty bin"))
            continue

        # Try consolidation (same SKU–Batch)
        cons, freed = consolidate_batch(row, wms_bins)
        if freed:
            ims += cons
            ims += distribute_batch(row, wms_bins, freed[:1])
            diagnostics.append((sku, batch, "CONSOLIDATED → DISTRIBUTED"))
        else:
            diagnostics.append((sku, batch, "MANUAL INTERVENTION REQUIRED"))

    return ims, diagnostics


# ==================================================
# UI
# ==================================================

st.sidebar.header("📂 Upload Files")

ptl_file = st.sidebar.file_uploader("PTL Demand File", type="xlsx")
sap_file = st.sidebar.file_uploader("SAP Inventory File", type="xlsx")
wms_file = st.sidebar.file_uploader("WMS Inventory File", type="xlsx")
sku_file = st.sidebar.file_uploader("SKU–Bin Mapping File", type="xlsx")

run = st.sidebar.button("▶ Run Engine")

if run and all([ptl_file, wms_file, sku_file]):

    ptl = load_ptl_demand(ptl_file)
    wms = load_wms_inventory(wms_file)
    sku_map = load_sku_master(sku_file)

    wms_bins, wms_summary = build_wms_state(wms)

    ims, diag = generate_ims(ptl, wms_bins, wms_summary, sku_map)

    im_df = pd.DataFrame(ims, columns=[
        "Source Bin", "HU Code", "SKU", "Batch",
        "Quality", "UOM", "Quantity",
        "Destination Bin", "Pick HU"
    ])

    diag_df = pd.DataFrame(diag, columns=["SKU", "Batch", "Decision"])

    # ================= DASHBOARD =================
    st.subheader("📊 Decision Dashboard")
    st.dataframe(diag_df, use_container_width=True)

    # ================= PREVIEW ===================
    st.subheader("👀 IM Preview (Before Download)")
    st.dataframe(im_df, use_container_width=True)

    # ================= DOWNLOAD ==================
    st.subheader("⬇ Download IM File")
    st.success(f"Total IM rows generated: {len(im_df)}")

    output = BytesIO()
    im_df.to_excel(output, index=False)
    output.seek(0)

    st.download_button(
        "Download IM Excel",
        data=output,
        file_name="IM_Final.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
