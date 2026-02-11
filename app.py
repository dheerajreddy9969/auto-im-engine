import streamlit as st
import pandas as pd
from io import BytesIO

TOTAL_BINS_PER_BASEPACK = 8


# -----------------------------
# READ EXCEL
# -----------------------------
def read_excel(file):

    xls = pd.ExcelFile(file)

    demand = pd.read_excel(xls, "PTL Demand")
    sap = pd.read_excel(xls, "SAP Inventory")
    ptl = pd.read_excel(xls, "PTL Inventory")

    demand = demand.iloc[:, [0, 2]]
    demand.columns = ["SKU", "Demand Qty"]

    sap = sap.iloc[:, [1, 2, 3, 14, 17]]
    sap.columns = ["SKU", "Batch", "Stock Type", "Expiry Date", "Qty"]

    ptl = ptl.iloc[:, [1, 4, 12, 13, 17]]
    ptl.columns = ["Area Type", "Bin Code", "BASEPACK", "SKU", "Batch"]

    return demand, sap, ptl


# -----------------------------
# BUILD BASEPACK MAP
# -----------------------------
def build_basepack_map(ptl):

    ptl = ptl[ptl["Area Type"] == "PTL"]

    return dict(zip(ptl["SKU"], ptl["BASEPACK"]))


# -----------------------------
# FEFO ALLOCATION
# -----------------------------
def fefo_allocate(demand, sap, basepack_map):

    allocations = []

    top20 = demand.head(20)

    for _, row in top20.iterrows():

        sku = row["SKU"]
        demand_qty = row["Demand Qty"]

        sap_filtered = sap[
            (sap["SKU"] == sku) &
            (sap["Stock Type"] == "ATP_PICK")
        ].copy()

        sap_filtered = sap_filtered.sort_values("Expiry Date")

        remaining = demand_qty

        for _, srow in sap_filtered.iterrows():

            if remaining <= 0:
                break

            allocate = min(remaining, srow["Qty"])

            allocations.append({
                "BASEPACK": basepack_map.get(sku, "UNKNOWN"),
                "SKU": sku,
                "Batch": srow["Batch"],
                "Allocated Qty": allocate
            })

            remaining -= allocate

    return pd.DataFrame(allocations)


# -----------------------------
# BIN CALCULATION
# -----------------------------
def calculate_bins(df):

    results = []

    for basepack, group in df.groupby("BASEPACK"):

        total = group["Allocated Qty"].sum()

        group = group.copy()

        group["Bins Needed"] = (
            group["Allocated Qty"] / total * TOTAL_BINS_PER_BASEPACK
        ).round()

        diff = TOTAL_BINS_PER_BASEPACK - group["Bins Needed"].sum()

        if diff != 0:
            idx = group["Allocated Qty"].idxmax()
            group.loc[idx, "Bins Needed"] += diff

        results.append(group)

    return pd.concat(results)


# -----------------------------
# EXISTING BIN COUNT
# -----------------------------
def get_existing_bins(df, ptl):

    ptl = ptl[ptl["Area Type"] == "PTL"]

    counts = (
        ptl.groupby(["BASEPACK", "SKU", "Batch"])
        ["Bin Code"]
        .nunique()
        .reset_index()
    )

    counts.rename(columns={"Bin Code": "Bins Present"}, inplace=True)

    df = df.merge(
        counts,
        on=["BASEPACK", "SKU", "Batch"],
        how="left"
    )

    df["Bins Present"] = df["Bins Present"].fillna(0)

    return df


# -----------------------------
# WRITE EXCEL
# -----------------------------
def to_excel(df):

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="IM_Output")

    output.seek(0)

    return output


# -----------------------------
# STREAMLIT UI
# -----------------------------
st.title("Internal Movement Automation System")

uploaded_file = st.file_uploader(
    "Upload Excel file",
    type=["xlsx"]
)

if uploaded_file:

    st.success("File uploaded successfully")

    demand, sap, ptl = read_excel(uploaded_file)

    basepack_map = build_basepack_map(ptl)

    allocations = fefo_allocate(demand, sap, basepack_map)

    bins = calculate_bins(allocations)

    final = get_existing_bins(bins, ptl)

    st.subheader("IM Allocation Preview")

    st.dataframe(final)

    excel = to_excel(final)

    st.download_button(
        label="Download IM_Output.xlsx",
        data=excel,
        file_name="IM_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
