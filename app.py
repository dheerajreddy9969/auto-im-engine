import streamlit as st
import pandas as pd

st.set_page_config(page_title="Auto IM Engine", layout="wide")
st.title("Auto Internal Movement Generator")

st.markdown("Upload Inventory Snapshot and PTL Demand file. System will generate directly uploadable IM file.")

inv_file = st.file_uploader("Upload Inventory Snapshot", type=["xlsx"])
dem_file = st.file_uploader("Upload PTL Demand File", type=["xlsx"])

THRESHOLD = 55  # lines per bin


def generate_im(inv_df, dem_df):

    # ---------------- Inventory preprocessing ----------------
    inv_df = inv_df[inv_df.iloc[:, 2] == "PTL"]  # Column C = PTL

    inv_df["SKU_BATCH"] = (
        inv_df.iloc[:, 17]  # Column R
        .astype(str)
        .str.strip()
        .str.upper()
    )

    inv_df["SKU"] = inv_df.iloc[:, 13].astype(str).str.strip().str.upper()   # Column N
    inv_df["Batch"] = inv_df.iloc[:, 16].astype(str).str.strip().str.upper() # Column Q
    inv_df["Bin"] = inv_df.iloc[:, 4]   # Column E
    inv_df["Zone"] = inv_df.iloc[:, 3]  # Column D
    inv_df["Qty"] = inv_df.iloc[:, 24]  # Column Y

    # ---------------- Demand preprocessing ----------------
    dem_df["SKU_BATCH"] = (
        dem_df["Sku-batch"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    dem_df["Daily_Avg_Lines"] = dem_df["Lines"]
    dem_df["Daily_Avg_Qty"] = dem_df["Quantity"]

    # Top 30 by avg lines
    top30 = dem_df.sort_values("Daily_Avg_Lines", ascending=False).head(30)

    im_rows = []

    for _, row in top30.iterrows():
        sku_batch = row["SKU_BATCH"]
        daily_lines = row["Daily_Avg_Lines"]

        sku_inv = inv_df[inv_df["SKU_BATCH"] == sku_batch]
        if sku_inv.empty:
            continue

        bins = sku_inv["Bin"].unique()
        B = len(bins)

        avg_lines_per_bin = daily_lines / B
        pressure_index = avg_lines_per_bin / THRESHOLD

        if pressure_index <= 1:
            continue  # No IM

        zone = sku_inv.iloc[0]["Zone"]
        empty_bins = inv_df[(inv_df["Zone"] == zone) & (inv_df["Qty"] == 0)]

        sku = sku_inv.iloc[0]["SKU"]
        batch = sku_inv.iloc[0]["Batch"]

        # ---------- BALANCING ----------
        if not empty_bins.empty:
            to_bin = empty_bins.iloc[0]["Bin"]
            from_bin = sku_inv.groupby("Bin")["Qty"].sum().idxmax()

            total_qty = sku_inv["Qty"].sum()
            move_qty = round(total_qty / (B + 1))

            if move_qty > 0:
                im_rows.append([
                    from_bin, "", sku, batch,
                    "Good", "L0", move_qty, to_bin
                ])

        # ---------- CONSOLIDATION ----------
        else:
            non_top = inv_df[~inv_df["SKU_BATCH"].isin(top30["SKU_BATCH"])]
            candidates = non_top[non_top["Zone"] == zone]

            if candidates.empty:
                continue  # manual case ignored

            donor = candidates.iloc[0]
            from_bin = donor["Bin"]
            to_bin = sku_inv.groupby("Bin")["Qty"].sum().idxmin()
            move_qty = donor["Qty"]

            if move_qty > 0:
                im_rows.append([
                    from_bin, "", donor["SKU"], donor["Batch"],
                    "Good", "L0", move_qty, to_bin
                ])

    # ---------------- Output ----------------
    im_df = pd.DataFrame(im_rows,
                         columns=["A","B","C","D","E","F","G","H"])
    return im_df


if st.button("Generate IM"):
    if inv_file and dem_file:
        inv_df = pd.read_excel(inv_file)
        dem_df = pd.read_excel(dem_file)

        im_df = generate_im(inv_df, dem_df)

        filename = "Internal Movement.xlsx"
        im_df.to_excel(filename, index=False)

        with open(filename, "rb") as f:
            st.download_button(
                "Download IM File",
                data=f,
                file_name=filename
            )
    else:
        st.error("Please upload both files.")
