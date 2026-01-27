import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="Auto IM Engine", layout="wide")
st.title("Auto Internal Movement Generator")

st.markdown("Upload Inventory Snapshot and PTL Demand file. System will generate directly uploadable IM file.")

inv_file = st.file_uploader("Upload Inventory Snapshot (.xlsx, Sheet: 'HU Level')", type=["xlsx"])
dem_file = st.file_uploader("Upload PTL Demand File", type=["xlsx"])

THRESHOLD = 55  # lines per bin

# HARDCODED BIN MASTER (Zones V001 to V008)
BIN_MASTER_DATA = {
    'Bin Code': ['V005-D1-L1-B001', 'V001-D1-L1-B002', 'V001-D1-L1-B003', 'V006-D1-L3-B012', 
                 'V001-D1-L1-B011', 'V001-D1-L1-B012', 'V004-D1-L1-B011', 'V007-D1-L1-B014',
                 'V001-D1-L2-B001', 'V001-D1-L2-B002', 'V001-D1-L2-B003', 'V001-D1-L2-B004',
                 'V001-D1-L2-B011', 'V001-D1-L2-B012', 'V001-D1-L2-B013', 'V001-D1-L2-B014',
                 'V001-D1-L3-B001', 'V001-D1-L3-B002', 'V001-D1-L3-B003', 'V001-D1-L3-B004',
                 'V001-D1-L3-B011', 'V001-D1-L3-B012', 'V001-D1-L3-B013', 'V001-D1-L3-B014',
                 'V001-D1-L4-B001', 'V001-D1-L4-B002', 'V001-D1-L4-B003', 'V001-D1-L4-B004',
                 'V002-D1-L1-B001', 'V002-D1-L1-B002', 'V002-D1-L1-B003', 'V002-D1-L1-B004',
                 'V002-D1-L1-B011', 'V002-D1-L1-B012', 'V002-D1-L1-B013', 'V002-D1-L1-B014',
                 'V002-D1-L2-B001', 'V002-D1-L2-B002', 'V002-D1-L2-B003', 'V002-D1-L2-B004',
                 'V002-D1-L2-B011', 'V002-D1-L2-B012', 'V002-D1-L2-B013', 'V002-D1-L2-B014',
                 'V002-D1-L3-B001', 'V002-D1-L3-B002', 'V002-D1-L3-B003', 'V002-D1-L3-B004',
                 'V002-D1-L3-B011', 'V002-D1-L3-B012', 'V002-D1-L3-B013', 'V002-D1-L3-B014',
                 'V002-D1-L4-B001', 'V002-D1-L4-B002', 'V002-D1-L4-B003', 'V002-D1-L4-B004',
                 'V003-D1-L1-B001', 'V003-D1-L1-B002', 'V003-D1-L1-B003', 'V003-D1-L1-B004',
                 'V003-D1-L1-B011', 'V003-D1-L1-B012', 'V003-D1-L1-B013', 'V003-D1-L1-B014',
                 'V003-D1-L2-B001', 'V003-D1-L2-B002', 'V003-D1-L2-B003', 'V003-D1-L2-B004',
                 'V003-D1-L2-B011', 'V003-D1-L2-B012', 'V003-D1-L2-B013', 'V003-D1-L2-B014',
                 'V003-D1-L3-B001', 'V003-D1-L3-B002', 'V003-D1-L3-B003', 'V003-D1-L3-B004',
                 'V003-D1-L3-B011', 'V003-D1-L3-B012', 'V003-D1-L3-B013', 'V003-D1-L3-B014',
                 'V003-D1-L4-B001', 'V003-D1-L4-B002', 'V003-D1-L4-B003', 'V003-D1-L4-B004',
                 'V004-D1-L1-B001', 'V004-D1-L1-B002', 'V004-D1-L1-B003', 'V004-D1-L1-B004',
                 'V004-D1-L1-B012', 'V004-D1-L1-B013', 'V004-D1-L1-B014', 'V004-D1-L2-B001',
                 'V004-D1-L2-B002', 'V004-D1-L2-B003', 'V004-D1-L2-B004', 'V004-D1-L2-B011',
                 'V004-D1-L2-B012', 'V004-D1-L2-B013', 'V004-D1-L2-B014', 'V004-D1-L3-B001',
                 'V004-D1-L3-B002', 'V004-D1-L3-B003', 'V004-D1-L3-B004', 'V004-D1-L3-B011',
                 'V004-D1-L3-B012', 'V004-D1-L3-B013', 'V004-D1-L3-B014', 'V004-D1-L4-B001',
                 'V004-D1-L4-B002', 'V004-D1-L4-B003', 'V004-D1-L4-B004', 'V005-D1-L1-B002',
                 'V005-D1-L1-B003', 'V005-D1-L1-B004', 'V005-D1-L1-B011', 'V005-D1-L1-B012',
                 'V005-D1-L1-B013', 'V005-D1-L1-B014', 'V005-D1-L2-B001', 'V005-D1-L2-B002',
                 'V005-D1-L2-B003', 'V005-D1-L2-B004', 'V005-D1-L2-B011', 'V005-D1-L2-B012',
                 'V005-D1-L2-B013', 'V005-D1-L2-B014', 'V005-D1-L3-B001', 'V005-D1-L3-B002',
                 'V005-D1-L3-B003', 'V005-D1-L3-B004', 'V005-D1-L3-B011', 'V005-D1-L3-B012',
                 'V005-D1-L3-B013', 'V005-D1-L3-B014', 'V005-D1-L4-B001', 'V005-D1-L4-B002',
                 'V005-D1-L4-B003', 'V005-D1-L4-B004', 'V006-D1-L1-B001', 'V006-D1-L1-B002',
                 'V006-D1-L1-B003', 'V006-D1-L1-B004', 'V006-D1-L1-B011', 'V006-D1-L1-B012',
                 'V006-D1-L1-B013', 'V006-D1-L1-B014', 'V006-D1-L2-B001', 'V006-D1-L2-B002',
                 'V006-D1-L2-B003', 'V006-D1-L2-B004', 'V006-D1-L2-B011', 'V006-D1-L2-B012',
                 'V006-D1-L2-B013', 'V006-D1-L2-B014', 'V006-D1-L3-B001', 'V006-D1-L3-B002',
                 'V006-D1-L3-B003', 'V006-D1-L3-B004', 'V006-D1-L3-B011', 'V006-D1-L3-B013',
                 'V006-D1-L3-B014', 'V006-D1-L4-B001', 'V006-D1-L4-B002', 'V006-D1-L4-B003',
                 'V006-D1-L4-B004', 'V007-D1-L1-B001', 'V007-D1-L1-B002', 'V007-D1-L1-B003',
                 'V007-D1-L1-B004', 'V007-D1-L1-B011', 'V007-D1-L1-B012', 'V007-D1-L1-B013',
                 'V007-D1-L2-B001', 'V007-D1-L2-B002', 'V007-D1-L2-B003', 'V007-D1-L2-B004',
                 'V007-D1-L2-B011', 'V007-D1-L2-B012', 'V007-D1-L2-B013', 'V007-D1-L2-B014',
                 'V007-D1-L3-B001', 'V007-D1-L3-B002', 'V007-D1-L3-B003', 'V007-D1-L3-B004',
                 'V007-D1-L3-B011', 'V007-D1-L3-B012', 'V007-D1-L3-B013', 'V007-D1-L3-B014',
                 'V007-D1-L4-B001', 'V007-D1-L4-B002', 'V007-D1-L4-B003', 'V007-D1-L4-B004',
                 'V008-D1-L1-B001', 'V008-D1-L1-B002', 'V008-D1-L1-B003', 'V008-D1-L1-B004',
                 'V008-D1-L1-B011', 'V008-D1-L1-B012', 'V008-D1-L1-B013', 'V008-D1-L1-B014',
                 'V008-D1-L2-B001', 'V008-D1-L2-B002', 'V008-D1-L2-B003', 'V008-D1-L2-B004',
                 'V008-D1-L2-B011', 'V008-D1-L2-B012', 'V008-D1-L2-B013', 'V008-D1-L2-B014',
                 'V008-D1-L3-B001', 'V008-D1-L3-B002', 'V008-D1-L3-B003', 'V008-D1-L3-B004',
                 'V008-D1-L3-B011', 'V008-D1-L3-B012', 'V008-D1-L3-B013', 'V008-D1-L3-B014',
                 'V008-D1-L4-B001', 'V008-D1-L4-B002', 'V008-D1-L4-B003', 'V008-D1-L4-B004'],
    'Product Code': [10016, 16013, 16232, 10016, 10016, 12026, 10016, 11047, 11047, 11156, 
                     16013, 16232, 16013, 12026, 12026, 11047, 11047, 11156, 16013, 16232,
                     16013, 12026, 12026, 11047, 11047, 11156, 16013, 16232, 11022, 11047,
                     11156, 16013, 16013, 12026, 12026, 11047, 11022, 11047, 11156, 16013,
                     16013, 12026, 12026, 11047, 11022, 11047, 11156, 16013, 16013, 12026,
                     12026, 11047, 11022, 11047, 11156, 16013, 11022, 11047, 11156, 16013,
                     16013, 12026, 12026, 11047, 11022, 11047, 11156, 16013, 16013, 12026,
                     12026, 11047, 11022, 11047, 11156, 16013, 16013, 12026, 12026, 11047,
                     11022, 11047, 11156, 16013, 10016, 16013, 16232, 10016, 12026, 12026,
                     11047, 11047, 11156, 16013, 16232, 16013, 12026, 12026, 11047, 11047,
                     11156, 16013, 16232, 16013, 12026, 12026, 11047, 11047, 11156, 16013,
                     16232, 10016, 16013, 16232, 10016, 10016, 12026, 12026, 11047, 11047,
                     11156, 16013, 16232, 16013, 12026, 12026, 11047, 11047, 11156, 16013,
                     16232, 16013, 10016, 12026, 11047, 11047, 11156, 16013, 16232, 10016,
                     16013, 16232, 10016, 11047, 16013, 16232, 10016, 16013, 12026, 12026,
                     11047, 11156, 16013, 16232, 16013, 12026, 12026, 11047, 11047, 11156,
                     16013, 16232, 16013, 12026, 12026, 11047, 11047, 11156, 16013, 16232,
                     11022, 11047, 11156, 16013, 16013, 12026, 12026, 11047, 11022, 11047,
                     11156, 16013, 16013, 12026, 12026, 11047, 11022, 11047, 11156, 16013,
                     16013, 12026, 12026, 11047, 11022, 11047, 11156, 16013]
}

BIN_MASTER = pd.DataFrame(BIN_MASTER_DATA)
BIN_MASTER['Zone'] = BIN_MASTER['Bin Code'].str.extract(r'(V\d+)')[0]


def generate_im(inv_df, dem_df):
    
    st.write("### 📊 Debug Information")
    st.write(f"Initial inventory shape: {inv_df.shape}")
    st.write(f"Initial demand shape: {dem_df.shape}")

    # ---------------- Inventory preprocessing ----------------
    # Column C filter for PTL
    inv_df = inv_df[inv_df.iloc[:, 2] == "PTL"].copy()
    st.write(f"After PTL filter: {inv_df.shape}")
    
    # Extract zone from Column D and filter zones 1-8
    inv_df['Zone'] = inv_df.iloc[:, 3].astype(str)  # Column D
    zone_nums = inv_df['Zone'].str.extract(r'(\d+)')[0].astype(float)
    inv_df = inv_df[zone_nums <= 8].copy()
    st.write(f"After Zone 1-8 filter: {inv_df.shape}")
    
    # Column N = SKU, Column Q = Batch
    inv_df['SKU'] = inv_df.iloc[:, 13].astype(str).str.strip().str.upper()  # Column N
    inv_df['Batch'] = inv_df.iloc[:, 16].astype(str).str.strip().str.upper()  # Column Q
    
    # Remove spaces, hyphens, underscores from both SKU and Batch before concatenation
    inv_df['SKU_clean'] = inv_df['SKU'].str.replace(' ', '').str.replace('-', '').str.replace('_', '')
    inv_df['Batch_clean'] = inv_df['Batch'].str.replace(' ', '').str.replace('-', '').str.replace('_', '')
    
    # Concatenate with NO separator
    inv_df['SKU_BATCH'] = inv_df['SKU_clean'] + inv_df['Batch_clean']
    
    inv_df['Bin'] = inv_df.iloc[:, 4].astype(str)  # Column E
    inv_df['Qty'] = pd.to_numeric(inv_df.iloc[:, 24], errors='coerce').fillna(0)  # Column Y
    
    st.write("Sample inventory SKU_BATCH values:")
    st.write(inv_df[['SKU', 'Batch', 'SKU_BATCH', 'Bin', 'Zone', 'Qty']].head(10))

    # ---------------- Demand preprocessing ----------------
    st.write("\n### 📋 Demand File Analysis")
    st.write("Demand file columns:", dem_df.columns.tolist())
    
    # Verify required columns exist
    if 'Sku-batch' not in dem_df.columns or 'Lines' not in dem_df.columns or 'Quantity' not in dem_df.columns:
        st.error("❌ Demand file must have columns: 'Sku-batch', 'Lines', 'Quantity'")
        return pd.DataFrame()
    
    # Clean SKU_BATCH in demand file (remove spaces, hyphens, underscores)
    dem_df['SKU_BATCH'] = (
        dem_df['Sku-batch']
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(' ', '')
        .str.replace('-', '')
        .str.replace('_', '')
    )
    
    dem_df['Daily_Avg_Lines'] = pd.to_numeric(dem_df['Lines'], errors='coerce').fillna(0)
    dem_df['Daily_Avg_Qty'] = pd.to_numeric(dem_df['Quantity'], errors='coerce').fillna(0)

    # Top 30 by avg lines
    top30 = dem_df.sort_values('Daily_Avg_Lines', ascending=False).head(30)
    
    st.write(f"\n### 🔝 Top 30 SKU-Batches by Lines:")
    st.dataframe(top30[['SKU_BATCH', 'Daily_Avg_Lines', 'Daily_Avg_Qty']].head(15))

    im_rows = []
    debug_info = []

    for idx, row in top30.iterrows():
        sku_batch = row['SKU_BATCH']
        daily_lines = row['Daily_Avg_Lines']

        sku_inv = inv_df[inv_df['SKU_BATCH'] == sku_batch].copy()
        
        if sku_inv.empty:
            debug_info.append(f"❌ {sku_batch}: Not found in inventory")
            continue

        bins = sku_inv['Bin'].unique()
        B = len(bins)

        avg_lines_per_bin = daily_lines / B
        pressure_index = avg_lines_per_bin / THRESHOLD

        debug_info.append(f"📊 {sku_batch}: {B} bins, {daily_lines:.1f} lines/day, {avg_lines_per_bin:.1f} lines/bin, pressure={pressure_index:.2f}")

        if pressure_index <= 1:
            debug_info.append(f"   ⏭️  Pressure OK (≤1), no IM needed")
            continue

        zone = sku_inv.iloc[0]['Zone']
        
        # Find empty bins in the same zone using bin master
        zone_bins_master = BIN_MASTER[BIN_MASTER['Zone'] == zone]['Bin Code'].tolist()
        occupied_bins = inv_df[inv_df['Zone'] == zone]['Bin'].unique().tolist()
        empty_bins_list = [b for b in zone_bins_master if b not in occupied_bins]
        
        # Also check inventory bins with Qty = 0
        zero_qty_bins = inv_df[(inv_df['Zone'] == zone) & (inv_df['Qty'] == 0)]['Bin'].unique().tolist()
        empty_bins_list.extend(zero_qty_bins)
        empty_bins_list = list(set(empty_bins_list))  # Remove duplicates

        # Get original SKU and Batch (before cleaning)
        sku = sku_inv.iloc[0]['SKU']
        batch = sku_inv.iloc[0]['Batch']

        # ---------- BALANCING ----------
        if len(empty_bins_list) > 0:
            debug_info.append(f"   ✅ BALANCING: Found {len(empty_bins_list)} empty bins in zone {zone}")
            
            to_bin = empty_bins_list[0]
            
            # Find bin with maximum quantity
            bin_qty = sku_inv.groupby('Bin')['Qty'].sum()
            from_bin = bin_qty.idxmax()

            total_qty = sku_inv['Qty'].sum()
            move_qty = round(total_qty / (B + 1))

            if move_qty > 0:
                im_rows.append({
                    'Source Bin': from_bin,
                    'HU Code (OPTIONAL)': '',
                    'SKU': sku,
                    'Batch': batch,
                    'Quality': 'Good',
                    'UOM': 'L0',
                    'Quantity': int(move_qty),
                    'Destination Bin (OPTIONAL)': to_bin,
                    'Pick HU (TRUE/FALSE)': ''
                })
                debug_info.append(f"   ➡️  Move {move_qty} units from {from_bin} to {to_bin}")

        # ---------- CONSOLIDATION ----------
        else:
            debug_info.append(f"   🔄 CONSOLIDATION: No empty bins in zone {zone}")
            
            # Find non-top 30 SKU-Batches in the same zone
            top30_skubatch_list = top30['SKU_BATCH'].tolist()
            non_top = inv_df[~inv_df['SKU_BATCH'].isin(top30_skubatch_list)].copy()
            candidates = non_top[non_top['Zone'] == zone]

            if candidates.empty:
                debug_info.append(f"   ⚠️  No consolidation candidates, manual intervention needed")
                continue

            # Get first candidate with quantity > 0
            candidates = candidates[candidates['Qty'] > 0]
            if candidates.empty:
                debug_info.append(f"   ⚠️  No candidates with qty > 0")
                continue
                
            donor = candidates.iloc[0]
            from_bin = donor['Bin']
            
            # Find bin with minimum quantity for this top 30 SKU-Batch
            bin_qty = sku_inv.groupby('Bin')['Qty'].sum()
            to_bin = bin_qty.idxmin()
            
            move_qty = int(donor['Qty'])

            if move_qty > 0:
                im_rows.append({
                    'Source Bin': from_bin,
                    'HU Code (OPTIONAL)': '',
                    'SKU': donor['SKU'],
                    'Batch': donor['Batch'],
                    'Quality': 'Good',
                    'UOM': 'L0',
                    'Quantity': move_qty,
                    'Destination Bin (OPTIONAL)': to_bin,
                    'Pick HU (TRUE/FALSE)': ''
                })
                debug_info.append(f"   ➡️  Consolidate: Move {move_qty} of {donor['SKU_BATCH']} from {from_bin} to {to_bin}")

    # Show debug info
    st.write("\n### 📝 Processing Log:")
    for msg in debug_info[:100]:
        st.text(msg)
    
    if len(debug_info) > 100:
        st.write(f"... and {len(debug_info) - 100} more entries")

    # ---------------- Output ----------------
    im_df = pd.DataFrame(im_rows)
    
    st.write(f"\n### ✅ Generated {len(im_df)} IM records")
    if len(im_df) > 0:
        st.dataframe(im_df.head(20))
    
    return im_df


if st.button("Generate IM", type="primary"):
    if inv_file and dem_file:
        try:
            # Read inventory from 'HU Level' sheet
            inv_df = pd.read_excel(inv_file, sheet_name='HU Level')
            dem_df = pd.read_excel(dem_file)

            im_df = generate_im(inv_df, dem_df)

            if len(im_df) == 0:
                st.warning("⚠️ No IM records generated. Check the debug information above to understand why.")
            else:
                # Create Excel file in memory
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    im_df.to_excel(writer, index=False, sheet_name='Internal Movement')
                output.seek(0)
                
                st.download_button(
                    label="📥 Download IM File",
                    data=output,
                    file_name="Internal_Movement.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success(f"✅ Generated {len(im_df)} IM records successfully!")
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
    else:
        st.error("⚠️ Please upload both files.")

st.markdown("---")
st.markdown("**Configuration:**")
st.markdown(f"- Threshold: {THRESHOLD} lines per bin")
st.markdown(f"- Zones considered: V001 to V008")
st.markdown(f"- Hardcoded bin master: {len(BIN_MASTER)} bins")
