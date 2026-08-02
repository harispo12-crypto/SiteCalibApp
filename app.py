import io
import json
import math
import os
import gspread 
from google.oauth2.service_account 
import Credentials
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# =========================================================
# ⚙️ ข้อมูลเวอร์ชันและผู้พัฒนา
# =========================================================
APP_VERSION = "v1.1.0"
LAST_UPDATED = "2026-08-01"
DEVELOPER_NAME = "HARIS PODAM"
APP_SIGNATURE = (
    f"SiteCalibrationApp_{APP_VERSION}_{LAST_UPDATED} by_{DEVELOPER_NAME}"
)


# =========================================================
# 🛠️ Helper Functions: แปลงพิกัด Indian 1975 UTM -> WGS84 Lat/Lon
# =========================================================
def indian1975_to_wgs84_latlon(
    easting, northing, zone_number=47, northern_hemisphere=True
):
    """แปลงพิกัด UTM Indian 1975 (Ellipsoid Everest 1830) ไปเป็น WGS84 Latitude/Longitude สำหรับปักหมุดบน Google Maps / Leaflet"""
    # 1. Everest 1830 Ellipsoid Parameters
    a_ind = 6377276.345
    f_ind = 1.0 / 300.8017
    b_ind = a_ind * (1.0 - f_ind)
    e2_ind = (a_ind**2 - b_ind**2) / (a_ind**2)

    # Convert UTM Indian 1975 to Lat/Lon Indian 1975
    k0 = 0.9996
    x = easting - 500000.0
    y = northing if northern_hemisphere else northing - 10000000.0
    long0 = (zone_number - 1) * 6 - 180 + 3

    M = y / k0
    mu = M / (
        a_ind
        * (
            1.0
            - e2_ind / 4.0
            - 3.0 * (e2_ind**2) / 64.0
            - 5.0 * (e2_ind**3) / 256.0
        )
    )
    e1 = (1.0 - math.sqrt(1.0 - e2_ind)) / (1.0 + math.sqrt(1.0 - e2_ind))

    phi1 = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * (e1**3) / 32.0) * math.sin(2.0 * mu)
        + (21.0 * (e1**2) / 16.0 - 55.0 * (e1**4) / 32.0) * math.sin(4.0 * mu)
        + (151.0 * (e1**3) / 96.0) * math.sin(6.0 * mu)
    )

    N1 = a_ind / math.sqrt(1.0 - e2_ind * (math.sin(phi1) ** 2))
    T1 = math.tan(phi1) ** 2
    C1 = (e2_ind / (1.0 - e2_ind)) * (math.cos(phi1) ** 2)
    R1 = (a_ind * (1.0 - e2_ind)) / (
        (1.0 - e2_ind * (math.sin(phi1) ** 2)) ** 1.5
    )
    D = x / (N1 * k0)

    lat_ind = phi1 - (N1 * math.tan(phi1) / R1) * (
        (D**2) / 2.0
        - (
            5.0
            + 3.0 * T1
            + 10.0 * C1
            - 4.0 * (C1**2)
            - 9.0 * (e2_ind / (1.0 - e2_ind))
        )
        * (D**4)
        / 24.0
    )
    lon_ind = math.radians(long0) + (
        D
        - (1.0 + 2.0 * T1 + C1) * (D**3) / 6.0
        + (5.0 - 2.0 * C1 + 28.0 * T1 - 3.0 * (C1**2) + 24.0 * (T1**2))
        * (D**5)
        / 120.0
    ) / math.cos(phi1)

    # 2. Convert Geodetic (Indian 1975) -> Geocentric XYZ
    N_ind = a_ind / math.sqrt(1.0 - e2_ind * (math.sin(lat_ind) ** 2))
    h = 0.0  # Height above ellipsoid
    X_ind = (N_ind + h) * math.cos(lat_ind) * math.cos(lon_ind)
    Y_ind = (N_ind + h) * math.cos(lat_ind) * math.sin(lon_ind)
    Z_ind = (N_ind * (1.0 - e2_ind) + h) * math.sin(lat_ind)

    # 3. Datum Shift to WGS84 (Thailand Standard RTSD 3-Parameter Shift)
    dX, dY, dZ = 204.0, 837.0, 294.0
    X_wgs = X_ind + dX
    Y_wgs = Y_ind + dY
    Z_wgs = Z_ind + dZ

    # 4. Convert Geocentric XYZ -> WGS84 Geodetic (Lat/Lon)
    a_wgs = 6378137.0
    f_wgs = 1.0 / 298.257223563
    b_wgs = a_wgs * (1.0 - f_wgs)
    e2_wgs = (a_wgs**2 - b_wgs**2) / (a_wgs**2)
    e_prime2_wgs = (a_wgs**2 - b_wgs**2) / (b_wgs**2)

    p = math.sqrt(X_wgs**2 + Y_wgs**2)
    theta = math.atan2(Z_wgs * a_wgs, p * b_wgs)

    lat_wgs = math.atan2(
        Z_wgs + e_prime2_wgs * b_wgs * (math.sin(theta) ** 3),
        p - e2_wgs * a_wgs * (math.cos(theta) ** 3),
    )
    lon_wgs = math.atan2(Y_wgs, X_wgs)

    return math.degrees(lat_wgs), math.degrees(lon_wgs)


# ---------------------------------------------------------
# 1. ตั้งค่าหน้าเว็บ & Custom CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Site Calibration App (2D/3D)", page_icon="📐", layout="wide"
)

st.markdown(
    f"""
    <style>
    :root {{
        --bg-main: #f8fafc;
        --text-primary: #0f172a;
        --text-secondary: #475569;
        --card-bg: #ffffff;
        --card-border: #cbd5e1;
        --hero-bg: linear-gradient(135deg, #e0f2fe 0%, #dbeafe 50%, #eff6ff 100%);
        --metric-val-color: #0f172a;
    }}

    @media (prefers-color-scheme: dark) {{
        :root {{
            --bg-main: #0f172a;
            --text-primary: #f8fafc;
            --text-secondary: #cbd5e1;
            --card-bg: #1e293b;
            --card-border: #334155;
            --hero-bg: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            --metric-val-color: #38bdf8;
        }}
    }}

    .stApp {{ background-color: var(--bg-main); color: var(--text-primary); }}
    .hero-container {{
        background: var(--hero-bg);
        padding: 1.8rem 2.2rem;
        border-radius: 16px;
        margin-bottom: 1.8rem;
        border: 1px solid var(--card-border);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
    }}
    .hero-title {{
        font-size: 2.1rem;
        font-weight: 800;
        margin: 0;
        color: var(--text-primary) !important;
    }}
    .badge-pill {{
        background: linear-gradient(90deg, #0284c7, #1d4ed8);
        color: #ffffff !important;
        padding: 0.35rem 0.85rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 700;
    }}
    [data-testid="stMetric"] {{
        background-color: var(--card-bg) !important;
        border-left: 5px solid #0284c7 !important;
        border: 1px solid var(--card-border);
        padding: 0.8rem 1rem !important;
        border-radius: 12px !important;
    }}
    [data-testid="stMetricValue"] {{ font-size: 1.45rem !important; font-weight: 800 !important; color: var(--metric-val-color) !important; }}
    .custom-footer {{ text-align: center; padding: 1.8rem 0; color: var(--text-secondary); font-size: 0.85rem; border-top: 1px solid var(--card-border); margin-top: 3rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# Header
st.markdown(
    f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <h1 class="hero-title">📐 โปรแกรมคำนวณและแปลงพิกัด Site Calibration</h1>
            <span class="badge-pill">{APP_VERSION}</span>
        </div>
        <p style="margin-top:0.5rem; margin-bottom:0; color: var(--text-secondary);">
            ระบบแปลงพิกัดท้องถิ่น (Local) เป็น UTM | วิเคราะห์ค่าความคลาดเคลื่อน (Residuals & RMSE) | พัฒนาโดย {DEVELOPER_NAME}
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Initialize Session State
if "calibrated" not in st.session_state:
    st.session_state.calibrated = False
if "params" not in st.session_state:
    st.session_state.params = {}
if "residuals_df" not in st.session_state:
    st.session_state.residuals_df = None
if "rmse_stats" not in st.session_state:
    st.session_state.rmse_stats = {}
if "tab2_result" not in st.session_state:
    st.session_state.tab2_result = None

# ---------------------------------------------------------
# 2. ป้อนข้อมูล GCP และเลือกโหมด
# ---------------------------------------------------------
st.header("1. ป้อนข้อมูลหมุดควบคุม (Ground Control Points - GCP)")

calc_mode = st.radio(
    "🎯 เลือกรูปแบบการคำนวณ Site Calibration:",
    ["2D (เฉพาะพิกัดราบ N, E)", "3D (พิกัดราบ + ความสูง N, E, Z)"],
    horizontal=True,
)
is_3d = "3D" in calc_mode

if is_3d:
    st.info(
        "✅ **โหมด 3D:** คำนวณปรับแก้ทั้งแนวราบและแนวสูง เหมาะสำหรับงานวิศวกรรม"
        " ถนน โครงสร้าง และพื้นที่ที่มีความต่างระดับสูง"
    )
else:
    st.info(
        "ℹ️ **โหมด 2D:** เหมาะสำหรับพื้นที่ราบใกล้ระดับน้ำทะเล\n\n⚠️"
        " *คำแนะนำ:* หากพื้นที่งานอยู่บนที่สูง (>100m จากระดับน้ำทะเล)"
        " แนะนำให้ใช้โหมด 3D เพื่อความถูกต้องของ Scale Factor"
    )

# Default Data Matrix
if is_3d:
    default_gcp = pd.DataFrame([
        {
            "Use": True,
            "Point": "GCP-01",
            "Local_N": 2000.000,
            "Local_E": 1000.000,
            "Local_Z": 10.000,
            "UTM_N": 1543210.456,
            "UTM_E": 654321.123,
            "UTM_Z": 12.500,
        },
        {
            "Use": True,
            "Point": "GCP-02",
            "Local_N": 2100.000,
            "Local_E": 1100.000,
            "Local_Z": 10.600,
            "UTM_N": 1543310.448,
            "UTM_E": 654421.135,
            "UTM_Z": 13.085,
        },
        {
            "Use": True,
            "Point": "GCP-03",
            "Local_N": 2200.000,
            "Local_E": 1200.000,
            "Local_Z": 11.500,
            "UTM_N": 1543410.465,
            "UTM_E": 654521.110,
            "UTM_Z": 13.980,
        },
        {
            "Use": False,
            "Point": "GCP-04",
            "Local_N": 2300.000,
            "Local_E": 1300.000,
            "Local_Z": 12.000,
            "UTM_N": 1543510.550,
            "UTM_E": 654621.200,
            "UTM_Z": 14.500,
        },
    ])
else:
    default_gcp = pd.DataFrame([
        {
            "Use": True,
            "Point": "GCP-01",
            "Local_N": 2000.000,
            "Local_E": 1000.000,
            "UTM_N": 1543210.456,
            "UTM_E": 654321.123,
        },
        {
            "Use": True,
            "Point": "GCP-02",
            "Local_N": 2100.000,
            "Local_E": 1100.000,
            "UTM_N": 1543310.448,
            "UTM_E": 654421.135,
        },
        {
            "Use": True,
            "Point": "GCP-03",
            "Local_N": 2200.000,
            "Local_E": 1200.000,
            "UTM_N": 1543410.465,
            "UTM_E": 654521.110,
        },
        {
            "Use": False,
            "Point": "GCP-04",
            "Local_N": 2300.000,
            "Local_E": 1300.000,
            "UTM_N": 1543510.550,
            "UTM_E": 654621.200,
        },
    ])

st.caption(
    "💡 **สามารถติ๊กเข้า/ออก ที่ช่อง Use"
    " เพื่อเลือกเปิดหรือปิดหมุด GCP ที่ใช้คำนวณได้ โดยช่อง Local คือ"
    " ค่าชั้นหนึ่งเดิม และช่อง UTM คือ ค่าชั้นหนึ่ง RTK**"
)

gcp_df = st.data_editor(
    default_gcp,
    num_rows="dynamic",
    key=f"gcp_editor_{is_3d}",
    use_container_width=True,
    column_config={
        "Use": st.column_config.CheckboxColumn("Use (ใช้งาน)", default=True)
    },
)

# ---------------------------------------------------------
# 3. คำนวณพารามิเตอร์ & ค่าความคลาดเคลื่อน (Residuals/RMSE)
# ---------------------------------------------------------
if st.button("🔄 คำนวณพารามิเตอร์ & วิเคราะห์ค่า Residuals", type="primary"):
    gcp_df.columns = gcp_df.columns.str.strip()
    active_gcp = gcp_df[gcp_df["Use"] == True].copy()

    req_cols = ["Local_N", "Local_E", "UTM_N", "UTM_E"]
    if is_3d:
        req_cols.extend(["Local_Z", "UTM_Z"])

    if all(col in active_gcp.columns for col in req_cols) and len(active_gcp) >= 1:
        used_cnt = len(active_gcp)

        if used_cnt == 1:
            lN_val, lE_val = (
                active_gcp["Local_N"].values[0],
                active_gcp["Local_E"].values[0],
            )
            uN_val, uE_val = (
                active_gcp["UTM_N"].values[0],
                active_gcp["UTM_E"].values[0],
            )
            scale_k = 1.0
            rotation_rad = 0.0
            dN = uN_val - lN_val
            dE = uE_val - lE_val
            dZ = (
                (
                    active_gcp["UTM_Z"].values[0]
                    - active_gcp["Local_Z"].values[0]
                )
                if is_3d
                else 0.0
            )
            is_single = True
        else:
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
                scale_k = 1.0
                rotation_rad = 0.0

            dN = mean_uN - (
                scale_k
                * (
                    mean_lE * np.sin(rotation_rad)
                    + mean_lN * np.cos(rotation_rad)
                )
            )
            dE = mean_uE - (
                scale_k
                * (
                    mean_lE * np.cos(rotation_rad)
                    - mean_lN * np.sin(rotation_rad)
                )
            )
            dZ = (
                np.mean(
                    active_gcp["UTM_Z"].values - active_gcp["Local_Z"].values
                )
                if is_3d
                else 0.0
            )
            is_single = False

        # --- คำนวณ Residuals และ RMSE ---
        calc_uN = dN + scale_k * (
            active_gcp["Local_E"] * np.sin(rotation_rad)
            + active_gcp["Local_N"] * np.cos(rotation_rad)
        )
        calc_uE = dE + scale_k * (
            active_gcp["Local_E"] * np.cos(rotation_rad)
            - active_gcp["Local_N"] * np.sin(rotation_rad)
        )

        v_N = active_gcp["UTM_N"] - calc_uN
        v_E = active_gcp["UTM_E"] - calc_uE
        v_2d = np.sqrt(v_N**2 + v_E**2)

        res_df = pd.DataFrame({
            "Point": active_gcp["Point"],
            "Res_N (m)": v_N.round(4),
            "Res_E (m)": v_E.round(4),
            "Res_2D (m)": v_2d.round(4),
        })

        rmse_N = np.sqrt(np.mean(v_N**2))
        rmse_E = np.sqrt(np.mean(v_E**2))
        rmse_2D = np.sqrt(np.mean(v_2d**2))
        rmse_Z = 0.0

        if is_3d:
            calc_uZ = active_gcp["Local_Z"] + dZ
            v_Z = active_gcp["UTM_Z"] - calc_uZ
            res_df["Res_Z (m)"] = v_Z.round(4)
            rmse_Z = np.sqrt(np.mean(v_Z**2))

        # บันทึกลง Session State
        st.session_state.params = {
            "dN": dN,
            "dE": dE,
            "dZ": dZ,
            "scale_k": scale_k,
            "rotation_rad": rotation_rad,
            "is_3d": is_3d,
            "used_count": used_cnt,
            "is_single": is_single,
            "active_gcp": active_gcp,
        }
        st.session_state.residuals_df = res_df
        st.session_state.rmse_stats = {
            "rmse_N": rmse_N,
            "rmse_E": rmse_E,
            "rmse_2D": rmse_2D,
            "rmse_Z": rmse_Z,
        }
        st.session_state.calibrated = True
        st.success("✅ คำนวณพารามิเตอร์และวิเคราะห์ค่า Residuals สำเร็จ!")
    else:
        st.error("⚠️ โปรดเลือกหมุดใช้งาน (Use = True) อย่างน้อย 1 จุด")

# ---------------------------------------------------------
# 4. แสดงพารามิเตอร์ & รายงานการวิเคราะห์ Residuals & RMSE
# ---------------------------------------------------------
if st.session_state.calibrated:
    params = st.session_state.params
    rmse = st.session_state.rmse_stats
    res_df = st.session_state.residuals_df
    rot_deg = np.degrees(params["rotation_rad"])

    st.markdown("---")
    st.subheader("📊 สรุปพารามิเตอร์ & ค่าความคลาดเคลื่อน (Residuals & RMSE)")

    if params["is_3d"]:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Shift Northing (ΔN)", f"{params['dN']:.3f} m")
        c2.metric("Shift Easting (ΔE)", f"{params['dE']:.3f} m")
        c3.metric("Shift Elevation (ΔZ)", f"{params['dZ']:.3f} m")
        c4.metric("Scale Factor (k)", f"{params['scale_k']:.6f}")
        c5.metric("Rotation Angle", f"{rot_deg:.4f}°")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Shift Northing (ΔN)", f"{params['dN']:.3f} m")
        c2.metric("Shift Easting (ΔE)", f"{params['dE']:.3f} m")
        c3.metric("Scale Factor (k)", f"{params['scale_k']:.6f}")
        c4.metric("Rotation Angle", f"{rot_deg:.4f}°")

    st.markdown("#### 🎯 ผลการวิเคราะห์ค่า RMSE (Root Mean Square Error)")

    if params["is_3d"]:
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("RMSE Northing", f"{rmse['rmse_N']:.4f} m")
        r2.metric("RMSE Easting", f"{rmse['rmse_E']:.4f} m")
        r3.metric("RMSE 2D (แนวราบ)", f"{rmse['rmse_2D']:.4f} m")
        r4.metric("RMSE Z (แนวสูง)", f"{rmse['rmse_Z']:.4f} m")
    else:
        r1, r2, r3 = st.columns(3)
        r1.metric("RMSE Northing", f"{rmse['rmse_N']:.4f} m")
        r2.metric("RMSE Easting", f"{rmse['rmse_E']:.4f} m")
        r3.metric("RMSE 2D (แนวราบ)", f"{rmse['rmse_2D']:.4f} m")

    st.markdown("#### 📋 ตารางแสดงค่า Residuals ของหมุด GCP แต่ละจุด")

    t_col1, t_col2 = st.columns(2)
    with t_col1:
        tol_2d = st.number_input(
            "เกณฑ์คลาดเคลื่อนแนวราบยอมรับได้ (Horizontal Tolerance - เมตร):",
            value=0.030,
            step=0.005,
            format="%.3f",
        )
    with t_col2:
        tol_z = st.number_input(
            "เกณฑ์คลาดเคลื่อนแนวสูงยอมรับได้ (Vertical Tolerance - เมตร):",
            value=0.050,
            step=0.005,
            format="%.3f",
        )

    display_res_df = res_df.copy()
    display_res_df["Status 2D"] = display_res_df["Res_2D (m)"].apply(
        lambda x: "✅ PASS" if abs(x) <= tol_2d else "⚠️ EXCEEDED"
    )

    if params["is_3d"]:
        display_res_df["Status Z"] = display_res_df["Res_Z (m)"].apply(
            lambda x: "✅ PASS" if abs(x) <= tol_z else "⚠️ EXCEEDED"
        )

    st.dataframe(display_res_df, use_container_width=True)

# =========================================================
# ☁️ ระบบเชื่อมต่อและจัดการข้อมูลผ่าน Google Sheets API
# =========================================================


@st.cache_resource
def get_gsheet_client():
    """สร้าง Client สำหรับเชื่อมต่อ Google Sheets API ผ่าน st.secrets"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    if "gcp_service_account" not in st.secrets:
        st.error(
            "❌ ไม่พบข้อมูล 'gcp_service_account' ใน .streamlit/secrets.toml"
        )
        st.stop()

    creds_dict = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(
        creds_dict, scopes=scopes
    )
    return gspread.authorize(credentials)


def safe_clean_dataframe(df):
    """ทำความสะอาดและแปลงชนิดข้อมูลให้ปลอดภัยสำหรับ Google Sheets/Dataframe"""
    if df is None or df.empty:
        return pd.DataFrame()

    clean_df = df.copy()

    # จัดการ Schema หลัก
    expected_cols = {
        "Show": bool,
        "Point_Name": str,
        "Local_N": float,
        "Local_E": float,
        "Local_Z": float,
        "UTM_N": float,
        "UTM_E": float,
        "UTM_Z": float,
        "Remark": str,
    }

    for col, dtype in expected_cols.items():
        if col not in clean_df.columns:
            if dtype == bool:
                clean_df[col] = True
            elif dtype == str:
                clean_df[col] = ""
            else:
                clean_df[col] = np.nan
        else:
            if dtype == str:
                clean_df[col] = clean_df[col].fillna("").astype(str)
            elif dtype == bool:
                # รองรับค่า True/False จาก Google Sheets ทั้ง boolean และ string
                clean_df[col] = (
                    clean_df[col]
                    .astype(str)
                    .str.upper()
                    .isin(["TRUE", "1", "YES"])
                )
            elif dtype == float:
                clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")

    return clean_df


def load_points_from_gsheets():
    """โหลด DataFrame จาก Google Sheets"""
    try:
        gc = get_gsheet_client()
        spreadsheet_url = st.secrets["gsheets"]["spreadsheet_url"]
        sh = gc.open_by_url(spreadsheet_url)
        worksheet = sh.get_worksheet(0)  # แผ่นงานแรก

        data = worksheet.get_all_records()
        if not data:
            return None
        df = pd.DataFrame(data)
        return safe_clean_dataframe(df)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูลจาก Google Sheets: {e}")
        return None


def save_points_to_gsheets(df):
    """บันทึก DataFrame ลง Google Sheets แบบเขียนทับทั้งหมด (Sync)"""
    try:
        gc = get_gsheet_client()
        spreadsheet_url = st.secrets["gsheets"]["spreadsheet_url"]
        sh = gc.open_by_url(spreadsheet_url)
        worksheet = sh.get_worksheet(0)

        clean_df = safe_clean_dataframe(df)

        # แทนค่า NaN / None ด้วยค่าว่างก่อนส่งเข้า Google Sheets
        clean_df_prepared = clean_df.fillna("")

        # เตรียมข้อมูล Header และ Values
        header = clean_df_prepared.columns.tolist()
        values = clean_df_prepared.values.tolist()
        data_to_update = [header] + values

        # ล้างข้อมูลเดิมและเขียนข้อมูลใหม่
        worksheet.clear()
        worksheet.update(data_to_update)
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึกข้อมูลลง Google Sheets: {e}")
        return False


# =========================================================
# 📍 ตารางบันทึกพิกัดหมุด + แผนที่ดาวเทียม Interactive Map
# =========================================================
st.markdown("---")
st.header("2. แสดงตำแหน่งหมุดบนแผนที่ดาวเทียม (Interactive Map)")

st.subheader("📍 ตารางบันทึกพิกัดหมุด (Local & UTM) เพื่อแสดงบนแผนที่")
st.caption(
    "💡 **ป้อนค่าพิกัดหมุด local(ชั้นหนึ่งเดิม) และ UTM(ชั้นหนึ่ง RTK)"
    " ที่ต้องการบันทึกในตารางนี้เพื่อรวบรวม"
    " หมุดจะถูกนำไปปักบนแผนที่ดาวเทียม"
    " และสามารถคลิกที่หมุดเพื่อเปิดดูค่า Local และ UTM"
    " ได้ตลอดเวลาในภายหลัง**"
)

# โหลดข้อมูลถาวรจาก Google Sheets หากยังไม่มีใน Session State
if "map_pts_df" not in st.session_state:
    saved_df = load_points_from_gsheets()
    if saved_df is not None and not saved_df.empty:
        st.session_state.map_pts_df = saved_df
    else:
        # Default Data กรณีเริ่มต้น หรือ Sheet ว่างเปล่า
        default_df = pd.DataFrame([
            {
                "Show": True,
                "Point_Name": "M-01",
                "Local_N": 2000.000,
                "Local_E": 1000.000,
                "Local_Z": 10.000,
                "UTM_N": 1543210.456,
                "UTM_E": 654321.123,
                "UTM_Z": 12.500,
                "Remark": "หมุดอาคาร A",
            },
            {
                "Show": True,
                "Point_Name": "M-02",
                "Local_N": 2100.000,
                "Local_E": 1100.000,
                "Local_Z": 10.600,
                "UTM_N": 1543310.448,
                "UTM_E": 654421.135,
                "UTM_Z": 13.085,
                "Remark": "หมุดรั้วด้านทิศเหนือ",
            },
        ])
        st.session_state.map_pts_df = safe_clean_dataframe(default_df)

# 1. แสดงตารางแก้ไขข้อมูล
map_editor_df = st.data_editor(
    st.session_state.map_pts_df,
    num_rows="dynamic",
    key="map_pts_editor",
    use_container_width=True,
    column_config={
        "Show": st.column_config.CheckboxColumn("แสดงหมุด", default=True),
        "Point_Name": st.column_config.TextColumn("ชื่อหมุด"),
        "Local_N": st.column_config.NumberColumn("Local N", format="%.3f"),
        "Local_E": st.column_config.NumberColumn("Local E", format="%.3f"),
        "Local_Z": st.column_config.NumberColumn("Local Z", format="%.3f"),
        "UTM_N": st.column_config.NumberColumn("UTM N", format="%.3f"),
        "UTM_E": st.column_config.NumberColumn("UTM E", format="%.3f"),
        "UTM_Z": st.column_config.NumberColumn("UTM Z", format="%.3f"),
        "Remark": st.column_config.TextColumn("หมายเหตุ"),
    },
)

# อัปเดตข้อมูลใน Session State อัตโนมัติ
st.session_state.map_pts_df = safe_clean_dataframe(map_editor_df)

# 2. ระบบควบคุมความปลอดภัยข้อมูล (Cloud Storage & Backup Hub)
with st.expander(
    "☁️ ระบบจัดการฐานข้อมูล Cloud (Google Sheets & Backup Hub)", expanded=True
):
    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

    with btn_col1:
        if st.button(
            "☁️ บันทึกลง Google Sheets", type="primary", use_container_width=True
        ):
            if save_points_to_gsheets(st.session_state.map_pts_df):
                st.success("✅ บันทึกข้อมูลลง Google Sheets เรียบร้อยแล้ว!")

    with btn_col2:
        if st.button(
            "🔄 ดึงข้อมูลล่าสุด (Reload Cloud)",
            type="secondary",
            use_container_width=True,
        ):
            reloaded = load_points_from_gsheets()
            if reloaded is not None:
                st.session_state.map_pts_df = reloaded
                st.rerun()

    with btn_col3:
        # Export JSON Backup
        export_json = json.dumps(
            st.session_state.map_pts_df.to_dict(orient="records"),
            ensure_ascii=False,
            indent=2,
        )
        st.download_button(
            label="📤 ส่งออกไฟล์สำรอง (.JSON)",
            data=export_json,
            file_name="site_calibration_points_backup.json",
            mime="application/json",
            use_container_width=True,
        )

    with btn_col4:
        # Export CSV Backup
        csv_buffer = st.session_state.map_pts_df.to_csv(index=False).encode(
            "utf-8-sig"
        )
        st.download_button(
            label="📊 ส่งออกตาราง (.CSV)",
            data=csv_buffer,
            file_name="site_calibration_points.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Option: Upload External Backup JSON / CSV
    uploaded_backup = st.file_uploader(
        "📥 นำเข้าไฟล์สำรอง (.JSON / .CSV) เพื่อกู้คืนพิกัดหมุดขึ้น Google Sheets:",
        type=["json", "csv"],
        key="backup_uploader",
    )
    if uploaded_backup is not None:
        try:
            if uploaded_backup.name.endswith(".json"):
                imported_records = json.load(uploaded_backup)
                imported_df = pd.DataFrame(imported_records)
            else:
                imported_df = pd.read_csv(uploaded_backup)

            clean_imported = safe_clean_dataframe(imported_df)
            st.session_state.map_pts_df = clean_imported

            # ซิงค์ลง Google Sheets ทันทีที่นำเข้า
            if save_points_to_gsheets(clean_imported):
                st.success(
                    "✅ นำเข้าและบันทึกข้อมูลลง Google Sheets เรียบร้อยแล้ว!"
                )
                st.rerun()
        except Exception as ex:
            st.error(f"❌ ไม่สามารถนำเข้าไฟล์ได้: {ex}")

# 3. ตัวเลือก Zone และการประมวลผลแผนที่
map_c1, _ = st.columns([1, 2])
with map_c1:
    zone_num = st.selectbox(
        "🗺️ เลือก UTM Zone (Indian 1975):",
        [47, 48, 46, 49],
        index=0,
        help="ประเทศไทย: Zone 47N (ภาคกลาง/เหนือ/ใต้) และ Zone 48N (ภาคอีสาน/ตะวันออก)",
    )

# แปลงพิกัด UTM (Indian 1975) -> Lat/Lon (WGS84) สำหรับ Leaflet
map_points = []
if "Show" in st.session_state.map_pts_df.columns:
    active_map_pts = st.session_state.map_pts_df[
        st.session_state.map_pts_df["Show"] == True
    ].copy()
    active_map_pts["UTM_E"] = pd.to_numeric(
        active_map_pts["UTM_E"], errors="coerce"
    )
    active_map_pts["UTM_N"] = pd.to_numeric(
        active_map_pts["UTM_N"], errors="coerce"
    )
    active_map_pts = active_map_pts.dropna(subset=["UTM_E", "UTM_N"])

    for _, row in active_map_pts.iterrows():
        try:
            # แปลงพิกัดจาก Indian 1975 เป็น WGS84 Lat/Lon (ใช้ฟังก์ชันเดิมของคุณ)
            lat_wgs, lon_wgs = indian1975_to_wgs84_latlon(
                row["UTM_E"], row["UTM_N"], zone_number=zone_num
            )

            pt_name = (
                str(row.get("Point_Name", "Point"))
                .replace("'", "\\'")
                .replace('"', '\\"')
            )
            remark_str = (
                str(row.get("Remark", ""))
                .replace("'", "\\'")
                .replace('"', '\\"')
            )

            loc_n = (
                f"{row['Local_N']:.3f}"
                if pd.notnull(row.get("Local_N"))
                else "-"
            )
            loc_e = (
                f"{row['Local_E']:.3f}"
                if pd.notnull(row.get("Local_E"))
                else "-"
            )
            loc_z = (
                f"{row['Local_Z']:.3f}"
                if pd.notnull(row.get("Local_Z"))
                else "-"
            )

            utm_n = f"{row['UTM_N']:.3f}"
            utm_e = f"{row['UTM_E']:.3f}"
            utm_z = (
                f"{row['UTM_Z']:.3f}" if pd.notnull(row.get("UTM_Z")) else "-"
            )

            popup_html = (
                f"<div style='font-family: sans-serif; font-size: 13px; line-height: 1.5;'>"
                f"<b style='font-size: 14px; color: #0284c7;'>📌 {pt_name}</b> "
                f"<span style='color: #64748b;'>({remark_str})</span><hr style='margin: 4px 0;'>"
                f"<b>📍 Local Coordinates:</b><br>"
                f"• Local N: {loc_n}<br>• Local E: {loc_e}<br>• Local Z: {loc_z}<br>"
                f"<div style='margin-top:4px;'><b>🌐 UTM (Indian 1975):</b><br>"
                f"• UTM N: {utm_n}<br>• UTM E: {utm_e}<br>• UTM Z: {utm_z}</div>"
                f"<div style='margin-top:4px; font-size:11px; color:#16a34a;'><b>🌍 Converted WGS84:</b><br>"
                f"• Lat: {lat_wgs:.6f}°, Lon: {lon_wgs:.6f}°</div>"
                f"</div>"
            )

            map_points.append({
                "name": pt_name,
                "lat": lat_wgs,
                "lon": lon_wgs,
                "info": popup_html,
            })
        except Exception:
            continue

# 4. แสดงผลบน Leaflet Map
if map_points:
    markers_js = ""
    bounds_list = []

    for p in map_points:
        markers_js += f"""
            L.circleMarker([{p['lat']}, {p['lon']}], {{
                radius: 8,
                fillColor: "#0284c7",
                color: "#ffffff",
                weight: 2,
                opacity: 1,
                fillOpacity: 0.9
            }}).bindPopup(`{p['info']}`).addTo(map);
            """
        bounds_list.append([p["lat"], p["lon"]])

    folium_map_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <style> #map {{ height: 480px; width: 100%; border-radius: 12px; }} </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                var map = L.map('map');

                var googleHybrid = L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={{x}}&y={{y}}&z={{z}}', {{
                    attribution: '&copy; Google Maps'
                }}).addTo(map);

                var googleSat = L.tileLayer('https://mt1.google.com/vt/lyrs=s&x={{x}}&y={{y}}&z={{z}}', {{
                    attribution: '&copy; Google Maps'
                }});

                var esriSat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                    attribution: 'Tiles &copy; Esri'
                }});

                var osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    attribution: '&copy; OpenStreetMap'
                }});

                var baseMaps = {{
                    "Google Hybrid (ดาวเทียม+ถนน)": googleHybrid,
                    "Google Satellite (ดาวเทียม)": googleSat,
                    "Esri World Imagery": esriSat,
                    "OpenStreetMap (ถนน)": osm
                }};
                L.control.layers(baseMaps).addTo(map);

                {markers_js}

                var bounds = {bounds_list};
                if (bounds.length > 0) {{
                    map.fitBounds(bounds, {{ padding: [30, 30], maxZoom: 18 }});
                }}
            </script>
        </body>
        </html>
        """
    components.html(folium_map_html, height=500)
else:
    st.info(
        "ℹ️ ยังไม่มีหมุดที่เปิดการแสดงผล (Show = True) หรือพิกัด UTM"
        " ในตารางไม่ถูกต้อง"
    )

# ---------------------------------------------------------
# 6. ส่วนแปลงพิกัดจุดงานใหม่หลายๆ จุด (Batch Transformation)
# ---------------------------------------------------------
if st.session_state.calibrated:
    st.markdown("---")
    st.header("3. แปลงพิกัดจุดงานใหม่เป็นพิกัด UTM (Batch Transformation)")

    params = st.session_state.params
    dN, dE, dZ = params["dN"], params["dE"], params["dZ"]
    scale_k, rotation_rad = params["scale_k"], params["rotation_rad"]

    tab1, tab2 = st.tabs(["📁 นำเข้าไฟล์", "✍️ กรอก/วาง ในตารางหน้าเว็บ"])

    with tab1:
        st.markdown(
            "💡 **รูปแบบไฟล์ที่รองรับ:** ไฟล์ Excel (`.xlsx`, `.xls`) หรือ CSV"
            " (`.csv`) โดยต้องมีหัวคอลัมน์ชื่อ **`Local_N`**, **`Local_E`** (และ"
            " **`Local_Z`** หากใช้โหมด 3D)"
        )

        uploaded_file = st.file_uploader(
            "เลือกไฟล์พิกัด Local (.xlsx, .csv, .txt)",
            type=["xlsx", "xls", "csv", "txt"],
            key="file_uploader",
        )
        if uploaded_file is not None:
            try:
                df_input = (
                    pd.read_excel(uploaded_file)
                    if uploaded_file.name.endswith((".xlsx", ".xls"))
                    else pd.read_csv(uploaded_file)
                )
                df_input.columns = df_input.columns.astype(str).str.strip()

                req_trans = ["Local_N", "Local_E"]
                if params["is_3d"]:
                    req_trans.append("Local_Z")

                if all(c in df_input.columns for c in req_trans):
                    df_result = df_input.copy()
                    df_result["UTM_N"] = dN + scale_k * (
                        df_input["Local_E"] * np.sin(rotation_rad)
                        + df_input["Local_N"] * np.cos(rotation_rad)
                    )
                    df_result["UTM_E"] = dE + scale_k * (
                        df_input["Local_E"] * np.cos(rotation_rad)
                        - df_input["Local_N"] * np.sin(rotation_rad)
                    )
                    if params["is_3d"]:
                        df_result["UTM_Z"] = df_input["Local_Z"] + dZ

                    st.success(f"✅ แปลงพิกัดสำเร็จ {len(df_result)} จุด")
                    st.dataframe(df_result, use_container_width=True)

                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                        df_result.to_excel(
                            writer, index=False, sheet_name="UTM_Coordinates"
                        )

                    st.download_button(
                        label="📥 ดาวน์โหลดไฟล์ผลลัพธ์ Excel (.xlsx)",
                        data=buffer.getvalue(),
                        file_name="Transformed_UTM_Points.xlsx",
                        mime=(
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        ),
                    )
                else:
                    st.error(
                        f"⚠️ ไฟล์ที่อัปโหลดต้องมีคอลัมน์: {', '.join(req_trans)}"
                    )
            except Exception as e:
                st.error(f"❌ ไม่สามารถอ่านไฟล์ได้: {e}")

    with tab2:
        new_pts_default = pd.DataFrame([
            (
                {
                    "Point_Name": "P-01",
                    "Local_N": 2000.500,
                    "Local_E": 1000.250,
                    "Local_Z": 10.150,
                }
                if params["is_3d"]
                else {
                    "Point_Name": "P-01",
                    "Local_N": 2000.500,
                    "Local_E": 1000.250,
                }
            )
        ])
        edited_new_df = st.data_editor(
            new_pts_default, num_rows="dynamic", use_container_width=True
        )

        if st.button("⚡ แปลงพิกัดในตาราง"):
            if not edited_new_df.empty:
                res_df_t2 = edited_new_df.copy()
                res_df_t2["UTM_N"] = dN + scale_k * (
                    edited_new_df["Local_E"] * np.sin(rotation_rad)
                    + edited_new_df["Local_N"] * np.cos(rotation_rad)
                )
                res_df_t2["UTM_E"] = dE + scale_k * (
                    edited_new_df["Local_E"] * np.cos(rotation_rad)
                    - edited_new_df["Local_N"] * np.sin(rotation_rad)
                )
                if params["is_3d"] and "Local_Z" in edited_new_df.columns:
                    # แก้ไข Bug การสร้าง UTM_Z
                    res_df_t2["UTM_Z"] = edited_new_df["Local_Z"] + dZ

                st.session_state.tab2_result = res_df_t2

        if st.session_state.tab2_result is not None:
            st.success("✅ แปลงพิกัดในตารางเรียบร้อยแล้ว")
            st.dataframe(st.session_state.tab2_result, use_container_width=True)

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.markdown(
    f"""
    <div class="custom-footer">
        <b>{APP_SIGNATURE}</b> | Developed with Streamlit & Python
    </div>
    """,
    unsafe_allow_html=True,
)
