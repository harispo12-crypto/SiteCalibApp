import io
import math
import json
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
import gspread
from google.oauth2.service_account import Credentials

# ตรวจสอบ GSheets Connection
try:
    from streamlit_gsheets import GSheetsConnection
    HAS_GSHEETS = True
except ImportError:
    HAS_GSHEETS = False

# =========================================================
# ⚙️ ข้อมูลโปรแกรม & ผู้พัฒนา
# =========================================================
APP_VERSION = "v1.0.0"
DEVELOPER_NAME = "HARIS PODAM"
TECH_STACK = "Python | Streamlit | Folium | Google Workspace"

# =========================================================
# 1. ตั้งค่าหน้าเว็บ & Custom CSS (Modern UI)
# =========================================================
st.set_page_config(page_title="Site Calibration & GIS Hub", page_icon="🌍", layout="wide")

st.markdown(
    """
    <style>
    :root {
        --bg-main: #f8fafc; --text-primary: #0f172a; --text-secondary: #475569;
        --card-bg: #ffffff; --card-border: #e2e8f0;
        --hero-bg: linear-gradient(135deg, #0284c7 0%, #1e40af 100%);
    }
    @media (prefers-color-scheme: dark) {
        :root {
            --bg-main: #0f172a; --text-primary: #f8fafc; --text-secondary: #94a3b8;
            --card-bg: #1e293b; --card-border: #334155;
            --hero-bg: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);
        }
    }
    .hero-container {
        background: var(--hero-bg); padding: 2rem 2.5rem; border-radius: 16px;
        margin-bottom: 2rem; color: white; box-shadow: 0 10px 25px rgba(0,0,0,0.1);
    }
    .hero-title { font-size: 2.2rem; font-weight: 900; margin: 0; color: white !important; letter-spacing: 0.5px; }
    .hero-subtitle { margin-top: 0.5rem; font-size: 1.1rem; opacity: 0.9; font-weight: 300; }
    
    [data-testid="stMetric"] {
        background-color: var(--card-bg) !important; border-top: 4px solid #0284c7 !important;
        border: 1px solid var(--card-border); padding: 1rem !important; border-radius: 12px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: transform 0.2s;
    }
    [data-testid="stMetric"]:hover { transform: translateY(-3px); }
    .custom-footer { text-align: center; padding: 2rem 0; margin-top: 3rem; color: var(--text-secondary); border-top: 1px dashed var(--card-border); font-size: 0.9rem; }
    
    /* Custom Popup Style for Folium */
    .map-popup { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 220px; }
    .map-popup h4 { color: #0284c7; margin-top: 0; margin-bottom: 8px; font-weight: 700; border-bottom: 2px solid #e2e8f0; padding-bottom: 4px; }
    .map-popup b { color: #334155; }
    .map-popup .coords { font-size: 12px; background: #f8fafc; padding: 6px; border-radius: 6px; margin-bottom: 5px; border: 1px solid #e2e8f0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="hero-container">
        <h1 class="hero-title">🌍 Site Calibration & GIS Database Hub</h1>
        <p class="hero-subtitle">ระบบคำนวณปรับแก้พิกัด (Local ↔ UTM) | จัดการฐานข้อมูลหมุด | แผนที่ภาพถ่ายดาวเทียม</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# 🛠️ Helper Functions
# =========================================================
def safe_clean_dataframe(df):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=[
            "Show", "Point_Name", "Local_N", "Local_E", "Local_Z", 
            "UTM_N", "UTM_E", "UTM_Z", "Remark"
        ])
    clean_df = df.copy()
    clean_df.columns = clean_df.columns.astype(str).str.strip()
    
    num_cols = ["Local_N", "Local_E", "Local_Z", "UTM_N", "UTM_E", "UTM_Z"]
    for col in num_cols:
        if col in clean_df.columns:
            clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce").fillna(0.0)
            
    if "Show" in clean_df.columns:
        clean_df["Show"] = clean_df["Show"].fillna(True).astype(bool)
    else:
        clean_df["Show"] = True
        
    for col in ["Point_Name", "Remark"]:
        if col in clean_df.columns:
            clean_df[col] = clean_df[col].fillna("").astype(str)
    return clean_df

def load_points_from_gsheets():
    if not HAS_GSHEETS: return pd.DataFrame()
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(ttl=0)
        if df is not None and not df.empty: return safe_clean_dataframe(df)
    except Exception:
        pass
    
    try:
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            client = gspread.authorize(creds)
            sheet_url = st.secrets.get("connections", {}).get("gsheets", {}).get("spreadsheet")
            if sheet_url:
                sheet = client.open_by_url(sheet_url).sheet1
                data = sheet.get_all_records()
                if data: return safe_clean_dataframe(pd.DataFrame(data))
    except Exception:
        pass
    return pd.DataFrame()

def save_points_to_gsheets(df):
    if not HAS_GSHEETS:
        st.error("❌ ขาดแพ็กเกจ st-gsheets-connection")
        return False
    if df is None or df.empty: return False
    
    save_df = safe_clean_dataframe(df).fillna("")
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        conn.update(data=save_df)
        return True
    except Exception as e1:
        try:
            if "gcp_service_account" in st.secrets:
                creds = Credentials.from_service_account_info(
                    st.secrets["gcp_service_account"], scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
                client = gspread.authorize(creds)
                sheet_url = st.secrets.get("connections", {}).get("gsheets", {}).get("spreadsheet")
                if sheet_url:
                    sheet = client.open_by_url(sheet_url).sheet1
                    sheet.clear()
                    sheet.update([save_df.columns.values.tolist()] + save_df.values.tolist())
                    return True
        except Exception:
            pass
        st.error(f"❌ บันทึกไม่สำเร็จ: {e1}")
        return False

def indian1975_to_wgs84_latlon(easting, northing, zone_number=47, northern_hemisphere=True):
    """แปลง UTM Indian 1975 เป็น WGS84 Lat/Lon"""
    a_ind, f_ind = 6377276.345, 1.0 / 300.8017
    b_ind = a_ind * (1.0 - f_ind)
    e2_ind = (a_ind**2 - b_ind**2) / (a_ind**2)

    k0 = 0.9996
    x = easting - 500000.0
    y = northing if northern_hemisphere else northing - 10000000.0
    long0 = (zone_number - 1) * 6 - 180 + 3

    M = y / k0
    mu = M / (a_ind * (1.0 - e2_ind / 4.0 - 3.0 * (e2_ind**2) / 64.0 - 5.0 * (e2_ind**3) / 256.0))
    e1 = (1.0 - math.sqrt(1.0 - e2_ind)) / (1.0 + math.sqrt(1.0 - e2_ind))

    phi1 = mu + (3.0 * e1 / 2.0 - 27.0 * (e1**3) / 32.0) * math.sin(2.0 * mu) + (21.0 * (e1**2) / 16.0 - 55.0 * (e1**4) / 32.0) * math.sin(4.0 * mu) + (151.0 * (e1**3) / 96.0) * math.sin(6.0 * mu)
    N1 = a_ind / math.sqrt(1.0 - e2_ind * (math.sin(phi1) ** 2))
    T1 = math.tan(phi1) ** 2
    C1 = (e2_ind / (1.0 - e2_ind)) * (math.cos(phi1) ** 2)
    R1 = (a_ind * (1.0 - e2_ind)) / ((1.0 - e2_ind * (math.sin(phi1) ** 2)) ** 1.5)
    D = x / (N1 * k0)

    lat_ind = phi1 - (N1 * math.tan(phi1) / R1) * ((D**2) / 2.0 - (5.0 + 3.0 * T1 + 10.0 * C1 - 4.0 * (C1**2) - 9.0 * (e2_ind / (1.0 - e2_ind))) * (D**4) / 24.0)
    lon_ind = math.radians(long0) + (D - (1.0 + 2.0 * T1 + C1) * (D**3) / 6.0 + (5.0 - 2.0 * C1 + 28.0 * T1 - 3.0 * (C1**2) + 24.0 * (T1**2)) * (D**5) / 120.0) / math.cos(phi1)

    N_ind = a_ind / math.sqrt(1.0 - e2_ind * (math.sin(lat_ind) ** 2))
    X_ind = N_ind * math.cos(lat_ind) * math.cos(lon_ind)
    Y_ind = N_ind * math.cos(lat_ind) * math.sin(lon_ind)
    Z_ind = (N_ind * (1.0 - e2_ind)) * math.sin(lat_ind)

    # 3-Parameter Shift (Indian 1975 to WGS84 - Thailand RTSD)
    X_wgs, Y_wgs, Z_wgs = X_ind + 204.0, Y_ind + 837.0, Z_ind + 294.0

    a_wgs, f_wgs = 6378137.0, 1.0 / 298.257223563
    b_wgs = a_wgs * (1.0 - f_wgs)
    e2_wgs = (a_wgs**2 - b_wgs**2) / (a_wgs**2)
    e_prime2_wgs = (a_wgs**2 - b_wgs**2) / (b_wgs**2)

    p = math.sqrt(X_wgs**2 + Y_wgs**2)
    theta = math.atan2(Z_wgs * a_wgs, p * b_wgs)
    lat_wgs = math.atan2(Z_wgs + e_prime2_wgs * b_wgs * (math.sin(theta) ** 3), p - e2_wgs * a_wgs * (math.cos(theta) ** 3))
    lon_wgs = math.atan2(Y_wgs, X_wgs)

    return math.degrees(lat_wgs), math.degrees(lon_wgs)

# =========================================================
# 🔄 Session State Initialization
# =========================================================
if "db_df" not in st.session_state: st.session_state.db_df = safe_clean_dataframe(load_points_from_gsheets())
if "calibrated" not in st.session_state: st.session_state.calibrated = False
if "params" not in st.session_state: st.session_state.params = {}
if "residuals_df" not in st.session_state: st.session_state.residuals_df = None
if "rmse_stats" not in st.session_state: st.session_state.rmse_stats = {}
if "map_center" not in st.session_state: st.session_state.map_center = [13.7563, 100.5018]
if "map_zoom" not in st.session_state: st.session_state.map_zoom = 6
if "searched_marker" not in st.session_state: st.session_state.searched_marker = None
if "trans_file_res" not in st.session_state: st.session_state.trans_file_res = None
if "trans_manual_res" not in st.session_state: st.session_state.trans_manual_res = None
if "map_update_trigger" not in st.session_state: st.session_state.map_update_trigger = 0  # ตัวกระตุ้นให้แผนที่ซูมใหม่

# =========================================================
# 🖥️ Main UI (Tabs)
# =========================================================
tab_calib, tab_trans, tab_db, tab_map = st.tabs([
    "📐 1. คำนวณ Calibration", 
    "⚡ 2. แปลงพิกัด", 
    "💾 3. ฐานข้อมูลหมุด", 
    "🗺️ 4. แผนที่ดาวเทียม"
])

# ---------------------------------------------------------
# TAB 1: คำนวณ Calibration
# ---------------------------------------------------------
with tab_calib:
    st.markdown("### คำนวณพารามิเตอร์ (Ground Control Points)")
    
    with st.expander("ℹ️ คำแนะนำ: การเลือกรูปแบบและวิธีการคำนวณ", expanded=True):
        st.markdown("""
        * **โหมด 2D (Helmert 4-Parameters):** ทำการปรับแก้เฉพาะแกนราบ (การเลื่อน ΔN, ΔE, การหมุน θ, การย่อขยาย k) เหมาะสำหรับงานสำรวจรังวัดที่ดินแนวราบทั่วไป
        * **โหมด 3D (Helmert 4-Param + Z-Shift):** ปรับแกนราบแบบ 2D และเพิ่มการคำนวณการเลื่อนแกนระดับ (ΔZ) เหมาะสำหรับงานก่อสร้างหรือพื้นที่ที่มีความต่างระดับสูง
        """)

    calc_mode = st.radio("เลือกรูปแบบการคำนวณ:", ["2D (ราบ N, E)", "3D (ราบ+ดิ่ง N, E, Z)"], horizontal=True)
    is_3d = "3D" in calc_mode

    default_gcp = pd.DataFrame([
        {"Use": True, "Point": "GCP-01", "Local_N": 2000.0, "Local_E": 1000.0, "Local_Z": 10.0 if is_3d else 0.0, "UTM_N": 1543210.456, "UTM_E": 654321.123, "UTM_Z": 12.5 if is_3d else 0.0},
        {"Use": True, "Point": "GCP-02", "Local_N": 2100.0, "Local_E": 1100.0, "Local_Z": 10.6 if is_3d else 0.0, "UTM_N": 1543310.448, "UTM_E": 654421.135, "UTM_Z": 13.085 if is_3d else 0.0},
    ])
    
    st.caption("ติ๊กถูกที่ช่อง 'Use' สำหรับหมุดที่ต้องการนำมาร่วมประมวลผล")
    gcp_df = st.data_editor(default_gcp, num_rows="dynamic", key=f"gcp_{is_3d}", use_container_width=True)

    st.markdown("**ตั้งค่าเกณฑ์ความคลาดเคลื่อน (Tolerance):**")
    col_tol1, col_tol2 = st.columns(2)
    tol_2d = col_tol1.number_input("เกณฑ์แนวราบยอมรับได้ (m)", value=0.030, step=0.005, format="%.3f")
    tol_z = col_tol2.number_input("เกณฑ์แนวดิ่งยอมรับได้ (m)", value=0.050, step=0.005, format="%.3f") if is_3d else 0.0

    if st.button("🔄 ประมวลผล Calibration", type="primary"):
        active_gcp = gcp_df[gcp_df["Use"] == True].copy()
        if len(active_gcp) >= 1:
            lN, lE = active_gcp["Local_N"].values, active_gcp["Local_E"].values
            uN, uE = active_gcp["UTM_N"].values, active_gcp["UTM_E"].values
            
            mean_lN, mean_lE = np.mean(lN), np.mean(lE)
            mean_uN, mean_uE = np.mean(uN), np.mean(uE)
            
            dx_l, dy_l = lE - mean_lE, lN - mean_lN
            dx_u, dy_u = uE - mean_uE, uN - mean_uN
            
            denom = np.sum(dx_l**2 + dy_l**2)
            if denom != 0:
                a = np.sum(dx_l * dx_u + dy_l * dy_u) / denom
                b = np.sum(dx_l * dy_u - dy_l * dx_u) / denom
                scale_k = np.sqrt(a**2 + b**2)
                rotation_rad = np.arctan2(b, a)
            else:
                scale_k, rotation_rad = 1.0, 0.0

            dN = mean_uN - (scale_k * (mean_lE * np.sin(rotation_rad) + mean_lN * np.cos(rotation_rad)))
            dE = mean_uE - (scale_k * (mean_lE * np.cos(rotation_rad) - mean_lN * np.sin(rotation_rad)))
            dZ = np.mean(active_gcp["UTM_Z"].values - active_gcp["Local_Z"].values) if is_3d else 0.0

            # หา Residuals
            calc_uN = dN + scale_k * (active_gcp["Local_E"] * np.sin(rotation_rad) + active_gcp["Local_N"] * np.cos(rotation_rad))
            calc_uE = dE + scale_k * (active_gcp["Local_E"] * np.cos(rotation_rad) - active_gcp["Local_N"] * np.sin(rotation_rad))

            v_N, v_E = active_gcp["UTM_N"] - calc_uN, active_gcp["UTM_E"] - calc_uE
            v_2d = np.sqrt(v_N**2 + v_E**2)

            res_df = pd.DataFrame({
                "Point": active_gcp["Point"], 
                "Res_N": v_N.round(4), 
                "Res_E": v_E.round(4), 
                "Res_2D": v_2d.round(4)
            })
            
            res_df["Status_2D"] = np.where(res_df["Res_2D"] <= tol_2d, "✅ PASS", "❌ FAIL")

            rmse_z = 0.0
            if is_3d:
                v_z = active_gcp["UTM_Z"] - (active_gcp["Local_Z"] + dZ)
                res_df["Res_Z"] = v_z.round(4)
                res_df["Status_Z"] = np.where(abs(res_df["Res_Z"]) <= tol_z, "✅ PASS", "❌ FAIL")
                rmse_z = np.sqrt(np.mean(v_z**2))
            
            st.session_state.params = {
                "dN": float(dN), "dE": float(dE), "dZ": float(dZ), 
                "scale_k": float(scale_k), "rotation_rad": float(rotation_rad), 
                "is_3d": bool(is_3d)
            }
            st.session_state.rmse_stats = {
                "rmse_N": float(np.sqrt(np.mean(v_N**2))), "rmse_E": float(np.sqrt(np.mean(v_E**2))), 
                "rmse_2D": float(np.sqrt(np.mean(v_2d**2))), "rmse_Z": float(rmse_z)
            }
            st.session_state.residuals_df = res_df
            st.session_state.calibrated = True
            st.success("✅ คำนวณสำเร็จ! ดูผลวิเคราะห์ด้านล่าง")
        else:
            st.error("⚠️ ต้องใช้ GCP อย่างน้อย 1 จุด")

    if st.session_state.calibrated:
        p = st.session_state.params
        st.markdown("---")
        
        param_json = json.dumps(p, indent=4)
        col_export, _ = st.columns([1, 4])
        col_export.download_button("📥 ดาวน์โหลด Parameter (.json)", data=param_json, file_name="calibration_params.json", mime="application/json", use_container_width=True)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Shift N (ΔN)", f"{p['dN']:.3f} m")
        c2.metric("Shift E (ΔE)", f"{p['dE']:.3f} m")
        if p["is_3d"]: c3.metric("Shift Z (ΔZ)", f"{p['dZ']:.3f} m")
        else: c3.metric("Shift Z (ΔZ)", "N/A (2D)")
        c4.metric("Scale (k)", f"{p['scale_k']:.6f}")
        
        st.markdown("#### 🎯 ผลตรวจสอบความคลาดเคลื่อน (Residuals Check)")
        st.dataframe(st.session_state.residuals_df, use_container_width=True)

# ---------------------------------------------------------
# TAB 2: แปลงพิกัด (Transformation)
# ---------------------------------------------------------
with tab_trans:
    st.markdown("### ⚡ ระบบแปลงพิกัด (Local to UTM)")
    if not st.session_state.calibrated:
        st.warning("⚠️ กรุณาไปคำนวณ Calibration ในแท็บที่ 1 ก่อน เพื่อหาพารามิเตอร์")
    else:
        p = st.session_state.params
        k, rot = p["scale_k"], p["rotation_rad"]
        
        t_manual, t_file = st.tabs(["✍️ กรอกข้อมูลลงตาราง (Manual)", "📂 นำเข้าไฟล์ (Excel / CSV / TXT)"])
        
        # --- แบบที่ 1: กรอกเอง ---
        with t_manual:
            st.markdown("กรอกพิกัด Local ที่ต้องการแปลง")
            if p["is_3d"]:
                def_manual = pd.DataFrame([{"Point_Name": "P-01", "Local_N": 2050.0, "Local_E": 1050.0, "Local_Z": 10.5, "Remark": "จุดทดสอบ"}])
            else:
                def_manual = pd.DataFrame([{"Point_Name": "P-01", "Local_N": 2050.0, "Local_E": 1050.0, "Remark": "จุดทดสอบ"}])
                
            manual_input_df = st.data_editor(def_manual, num_rows="dynamic", key="manual_trans", use_container_width=True)
            
            if st.button("🚀 คำนวณแปลงพิกัดในตาราง"):
                df_res_m = safe_clean_dataframe(manual_input_df)
                df_res_m["UTM_N"] = (p["dN"] + k * (df_res_m["Local_E"] * np.sin(rot) + df_res_m["Local_N"] * np.cos(rot))).round(3)
                df_res_m["UTM_E"] = (p["dE"] + k * (df_res_m["Local_E"] * np.cos(rot) - df_res_m["Local_N"] * np.sin(rot))).round(3)
                if p["is_3d"]: df_res_m["UTM_Z"] = (df_res_m["Local_Z"] + p["dZ"]).round(3)
                else: df_res_m["UTM_Z"] = 0.0
                df_res_m["Show"] = True
                
                st.session_state.trans_manual_res = df_res_m
                st.success("✅ แปลงพิกัดสำเร็จ!")
            
            if st.session_state.trans_manual_res is not None:
                st.dataframe(st.session_state.trans_manual_res, use_container_width=True)
                if st.button("💾 ส่งพิกัดเหล่านี้เข้าฐานข้อมูล (Tab 3)", key="save_manual"):
                    updated_db = pd.concat([st.session_state.db_df, st.session_state.trans_manual_res], ignore_index=True)
                    st.session_state.db_df = safe_clean_dataframe(updated_db)
                    save_points_to_gsheets(st.session_state.db_df)
                    st.session_state.trans_manual_res = None
                    st.success("✅ โอนเข้าฐานข้อมูลเรียบร้อย!")
                    st.rerun()

        # --- แบบที่ 2: อัปโหลดไฟล์ ---
        with t_file:
            st.info("💡 **รูปแบบไฟล์:** รองรับไฟล์ Excel (`.xlsx`, `.xls`) และ Text (`.csv`, `.txt`) \n\n📍 **คอลัมน์ที่บังคับให้มี:** `Point_Name`, `Local_N`, `Local_E` (และ `Local_Z` หากแปลงแบบ 3D)")
            uploaded_file = st.file_uploader("📂 เลือกไฟล์พิกัดที่ต้องการแปลง", type=["xlsx", "xls", "csv", "txt"])
            
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith(('.xlsx', '.xls')):
                        df_batch = pd.read_excel(uploaded_file)
                    else:
                        df_batch = pd.read_csv(uploaded_file)
                    
                    df_batch.columns = df_batch.columns.astype(str).str.strip()
                    req_cols = ["Local_N", "Local_E"]
                    if p["is_3d"]: req_cols.append("Local_Z")
                    
                    if not all(col in df_batch.columns for col in req_cols):
                        st.error(f"❌ ข้อมูลในไฟล์ขาดคอลัมน์ที่จำเป็น: กรุณาเตรียมหัวคอลัมน์ให้มี {', '.join(req_cols)}")
                    else:
                        if st.button("🚀 ประมวลผลไฟล์นี้เป็น UTM"):
                            df_res = df_batch.copy()
                            df_res["UTM_N"] = (p["dN"] + k * (df_res["Local_E"] * np.sin(rot) + df_res["Local_N"] * np.cos(rot))).round(3)
                            df_res["UTM_E"] = (p["dE"] + k * (df_res["Local_E"] * np.cos(rot) - df_res["Local_N"] * np.sin(rot))).round(3)
                            if p["is_3d"]: df_res["UTM_Z"] = (df_res["Local_Z"] + p["dZ"]).round(3)
                            else: df_res["UTM_Z"] = 0.0
                            df_res["Show"] = True
                            
                            if "Point_Name" not in df_res.columns: df_res["Point_Name"] = [f"P-{i+1}" for i in range(len(df_res))]
                            if "Remark" not in df_res.columns: df_res["Remark"] = "Batch Transform"
                            
                            st.session_state.trans_file_res = df_res
                            st.success("✅ คำนวณสำเร็จ!")
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
            
            if st.session_state.trans_file_res is not None:
                st.dataframe(st.session_state.trans_file_res, use_container_width=True)
                
                col_btn1, col_btn2 = st.columns(2)
                buffer = io.BytesIO()
                st.session_state.trans_file_res.to_excel(buffer, index=False)
                col_btn1.download_button("📥 ดาวน์โหลดผลลัพธ์ (Excel)", buffer.getvalue(), "UTM_Result.xlsx")
                
                if col_btn2.button("💾 ส่งจุดทั้งหมดเข้าฐานข้อมูลหมุด (Tab 3)", key="save_file"):
                    updated_db = pd.concat([st.session_state.db_df, st.session_state.trans_file_res], ignore_index=True)
                    st.session_state.db_df = safe_clean_dataframe(updated_db)
                    save_points_to_gsheets(st.session_state.db_df)
                    st.session_state.trans_file_res = None
                    st.success("✅ โอนเข้าฐานข้อมูลเรียบร้อย!")
                    st.rerun()

# ---------------------------------------------------------
# TAB 3: ฐานข้อมูลหมุด (Database)
# ---------------------------------------------------------
with tab_db:
    st.markdown("### 💾 ฐานข้อมูลพิกัดหมุด (Master Database)")
    
    with st.expander("➕ เพิ่มหมุดใหม่ (Manual)", expanded=False):
        with st.form("add_form", clear_on_submit=True):
            st.markdown("กรอกข้อมูลพิกัดที่ต้องการจัดเก็บ")
            c1, c2, c3 = st.columns(3)
            with c1:
                pt_name = st.text_input("ชื่อหมุด (Point Name)*")
                rem = st.text_input("หมายเหตุ (Remark)")
            with c2:
                st.markdown("**พิกัด UTM (WGS84 / Indian1975)**")
                un = st.number_input("UTM Northing", value=0.0, format="%.3f")
                ue = st.number_input("UTM Easting", value=0.0, format="%.3f")
                uz = st.number_input("UTM Elevation (Z)", value=0.0, format="%.3f")
            with c3:
                st.markdown("**พิกัดท้องถิ่น (Local System)**")
                ln = st.number_input("Local Northing", value=0.0, format="%.3f")
                le = st.number_input("Local Easting", value=0.0, format="%.3f")
                lz = st.number_input("Local Elevation (Z)", value=0.0, format="%.3f")
            
            if st.form_submit_button("บันทึกหมุดใหม่", type="primary"):
                if pt_name.strip():
                    new_r = pd.DataFrame([{"Show": True, "Point_Name": pt_name, "Local_N": ln, "Local_E": le, "Local_Z": lz, "UTM_N": un, "UTM_E": ue, "UTM_Z": uz, "Remark": rem}])
                    st.session_state.db_df = safe_clean_dataframe(pd.concat([st.session_state.db_df, new_r], ignore_index=True))
                    save_points_to_gsheets(st.session_state.db_df)
                    st.success("✅ บันทึกและอัปเดตลงฐานข้อมูลสำเร็จ!")
                    st.rerun()
                else:
                    st.warning("⚠️ กรุณาระบุชื่อหมุด")

    # ค้นหาและดูข้อมูล
    c_s, c_l = st.columns([3, 1])
    search_q = c_s.text_input("🔍 ค้นหา (พิมพ์ชื่อหมุด, หมายเหตุ หรือ พิกัด):")
    row_l = c_l.selectbox("จำนวนบรรทัด:", [10, 20, 50, "ทั้งหมด"])

    df_disp = st.session_state.db_df.copy()
    if search_q:
        q = search_q.lower()
        df_disp = df_disp[df_disp.astype(str).apply(lambda x: x.str.lower().str.contains(q)).any(axis=1)]
    
    df_disp = df_disp if row_l == "ทั้งหมด" else df_disp.head(int(row_l))
    st.dataframe(df_disp, use_container_width=True)
    
    # 🎯 ฟีเจอร์: เลือกหมุดเพื่อซูมไปแผนที่
    st.markdown("---")
    st.markdown("#### 🎯 ค้นหาเสร็จแล้ว เลือกหมุดเพื่อซูมบนแผนที่")
    valid_pts = df_disp[(df_disp["UTM_N"] > 0) & (df_disp["UTM_E"] > 0)]
    
    if not valid_pts.empty:
        col_sel, col_z, col_btn = st.columns([2, 1, 1])
        sel_pt = col_sel.selectbox("เลือกหมุดที่ต้องการดูบนแผนที่:", ["-- เลือก --"] + valid_pts["Point_Name"].tolist())
        sel_zone = col_z.selectbox("UTM Zone ของหมุดนี้:", [47, 48])
        
        st.write("") # เว้นบรรทัดให้ปุ่มตรงกัน
        if col_btn.button("🔎 ซูมไปยังหมุดนี้", type="primary"):
            if sel_pt != "-- เลือก --":
                p_data = valid_pts[valid_pts["Point_Name"] == sel_pt].iloc[0]
                lat, lon = indian1975_to_wgs84_latlon(p_data["UTM_E"], p_data["UTM_N"], zone_number=sel_zone)
                if lat:
                    st.session_state.map_center = [lat, lon]
                    st.session_state.map_zoom = 19
                    st.session_state.map_update_trigger += 1  # ทริกเกอร์ให้แผนที่บังคับซูมใหม่
                    st.session_state.searched_marker = {
                        "lat": lat, "lon": lon, 
                        "title": f"📍 {p_data['Point_Name']} (จากฐานข้อมูล)", 
                        "detail": f"Zone: {sel_zone}N<br>N: {p_data['UTM_N']:.3f}<br>E: {p_data['UTM_E']:.3f}"
                    }
                    st.success("✅ ล็อกเป้าหมายสำเร็จ! กรุณาคลิกแท็บ '4. แผนที่ดาวเทียม' เพื่อดูตำแหน่ง")
            else:
                st.warning("⚠️ กรุณาเลือกชื่อหมุดก่อนกดซูม")
    else:
        st.info("ไม่มีหมุดที่มีค่าพิกัด UTM สำหรับแสดงผลบนแผนที่")

    st.markdown("---")
    # ข้อความแจ้งเตือนแทนปุ่มอัปเดตแบบเก่า
    st.info("📌 **แจ้งเตือน:** ระบบจะทำการบันทึกข้อมูลอัตโนมัติเมื่อกดเพิ่มหมุด หากท่านต้องการ **แก้ไข (Edit)** หรือ **ลบ (Delete)** ข้อมูลพิกัดในฐานข้อมูล กรุณาติดต่อ **Admin (ผู้ดูแลระบบ)**")

# ---------------------------------------------------------
# TAB 4: แผนที่ภาพถ่ายดาวเทียม
# ---------------------------------------------------------
with tab_map:
    st.markdown("### 🗺️ แผนที่ภาพถ่ายดาวเทียม (Interactive Satellite Map)")
    
    st.markdown("**ปักหมุด ค้นหา พิกัดรังวัดลงบนแผนที่โลก**")
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    # สลับเอา N ขึ้นก่อน E ตามความต้องการ
    s_n = c1.number_input("UTM Northing (N)", value=0.0, format="%.3f")
    s_e = c2.number_input("UTM Easting (E)", value=0.0, format="%.3f")
    s_z = c3.selectbox("UTM Zone", [47, 48], key="map_zone")
    
    st.write("")
    if c4.button("📍 ซูมไปพิกัดนี้", type="primary"):
        if s_e > 0 and s_n > 0:
            lat, lon = indian1975_to_wgs84_latlon(s_e, s_n, zone_number=s_z)
            if lat:
                st.session_state.map_center = [lat, lon]
                st.session_state.map_zoom = 19
                st.session_state.map_update_trigger += 1 # ทริกเกอร์ให้แผนที่บังคับซูมใหม่
                st.session_state.searched_marker = {"lat": lat, "lon": lon, "title": "จุดค้นหา (Search)", "detail": f"Zone: {s_z}N<br>N: {s_n:,.3f}<br>E: {s_e:,.3f}"}
                st.rerun()

    st.markdown("---")
    
    # สร้างแผนที่ Folium
    m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, max_zoom=21)
    
    # เพิ่ม Base Maps ความละเอียดสูง
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Esri Satellite (Clear)').add_to(m)
    folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Google Hybrid (มีชื่อถนน)').add_to(m)
    folium.LayerControl().add_to(m)

    # ดึงหมุดจาก Database มาพล็อต (ออกแบบสัญลักษณ์และ Popup ให้สวยงาม)
    valid_db = st.session_state.db_df[(st.session_state.db_df["Show"] == True) & (st.session_state.db_df["UTM_N"] > 0)]
    
    for _, row in valid_db.iterrows():
        lat, lon = indian1975_to_wgs84_latlon(row["UTM_E"], row["UTM_N"], zone_number=s_z) 
        if lat:
            popup_html = f"""
            <div class="map-popup">
                <h4>📍 {row['Point_Name']}</h4>
                <div class="coords">
                    <b>LOCAL:</b><br>N: {row['Local_N']:.3f} | E: {row['Local_E']:.3f} | Z: {row['Local_Z']:.3f}
                </div>
                <div class="coords" style="background:#e0f2fe; border-color:#bae6fd;">
                    <b>UTM:</b><br>N: {row['UTM_N']:.3f} | E: {row['UTM_E']:.3f} | Z: {row['UTM_Z']:.3f}
                </div>
                <div style="font-size:12px; margin-top:8px;">
                    📝 <b>หมายเหตุ:</b> {row['Remark'] if row['Remark'] else '-'}
                </div>
            </div>
            """
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"คลิกดูข้อมูล: {row['Point_Name']}",
                icon=folium.Icon(color="cadetblue", icon="info-sign", prefix="glyphicon")
            ).add_to(m)

    # จุดค้นหา (Marker สีแดงพิเศษ)
    if st.session_state.searched_marker:
        sm = st.session_state.searched_marker
        popup_search = f"""
        <div class="map-popup">
            <h4 style="color:#ef4444;">🎯 {sm['title']}</h4>
            <div class="coords"><b>พิกัด:</b><br>{sm['detail']}</div>
            <div class="coords"><b>Lat/Lon:</b><br>{sm['lat']:.6f}, {sm['lon']:.6f}</div>
        </div>
        """
        folium.Marker(
            location=[sm["lat"], sm["lon"]], 
            popup=folium.Popup(popup_search, max_width=250),
            tooltip="จุดที่ท่านค้นหา", 
            icon=folium.Icon(color="red", icon="star", prefix="glyphicon")
        ).add_to(m)

    # แสดงผลบน Streamlit พร้อมบังคับซูมด้วย key และเพิ่มความเร็วด้วย returned_objects
    st_folium(
        m, 
        width="100%", 
        height=650, 
        key=f"map_{st.session_state.map_update_trigger}", 
        returned_objects=[]
    )

# =========================================================
# Footer
# =========================================================
st.markdown(
    f"""
    <div class="custom-footer">
        <b>Version:</b> {APP_VERSION} &nbsp;|&nbsp; <b>Developer:</b> {DEVELOPER_NAME} <br>
        <span style="opacity: 0.7; font-size: 0.8rem;">{TECH_STACK}</span>
    </div>
    """,
    unsafe_allow_html=True,
)
