import streamlit as st
import asyncio
import os
import shutil
import time
import zipfile
import io
import csv
import httpx
from datetime import date, datetime, timedelta

# ===========================
# 1. 工具函式 (原本的 date_utils & path_utils)
# ===========================
def parse_date(d: str | date) -> date:
    if isinstance(d, date): return d
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        return date.today()

def validate_dates(start_date: date, end_date: date):
    today = date.today()
    if start_date > end_date:
        return "起迄日不合法"
    if end_date == today:
        # 其實 API 可以抓今天，但為了保險通常抓到昨天，這裡先放寬
        pass 
    delta = (end_date - start_date).days
    return "正確", delta

def get_output_dir_path(vessel_id: str, temp_dir: str) -> str:
    return f"{temp_dir}/vessel_{vessel_id}"

# ===========================
# 2. 下載核心 (原本的 download_api)
# ===========================
async def fetch_vessel_track(api_key, vessel_id, from_date, to_date, output_dir):
    base_url = f"https://services.marinetraffic.com/api/exportvesseltrack/{api_key}"
    vessel_id = str(vessel_id).strip()
    
    # 自動判斷 ID 類型
    id_param = "MMSI" if len(vessel_id) == 9 else "imo"
    
    params = {
        "v": 3,
        "fromdate": str(from_date),
        "todate": str(to_date),
        id_param: vessel_id,
        "protocol": "csv",
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            
            filename = f"track_{vessel_id}_{from_date}_{to_date}.csv"
            os.makedirs(output_dir, exist_ok=True)
            with open(os.path.join(output_dir, filename), "wb") as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"Download Error: {e}")
        return False

async def download_task(api_key, vessel_id, start_date, end_date, temp_root):
    # 日期切分邏輯 (超過180天要切)
    current_start = start_date
    output_dir = get_output_dir_path(vessel_id, temp_root)
    
    if os.path.exists(output_dir): shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    all_success = True
    while current_start < end_date:
        current_end = current_start + timedelta(days=180)
        if current_end > end_date: current_end = end_date
        
        success = await fetch_vessel_track(api_key, vessel_id, current_start, current_end, output_dir)
        if not success: all_success = False
        
        current_start = current_end + timedelta(days=1)
        if current_start < end_date: await asyncio.sleep(1) # 小區段間稍微休息
            
    return all_success

# ===========================
# 3. 網頁介面 (Streamlit UI)
# ===========================
st.set_page_config(page_title="船舶軌跡下載器", page_icon="🚢", layout="wide")
st.title("🚢 船舶軌跡批次下載 (MMSI / IMO)")

with st.sidebar:
    st.header("⚙️ 設定")
    # 嘗試從 Secrets 讀取 Key，方便自己用
    default_key = st.secrets.get("MARINE_TRAFFIC_API_KEY", "")
    api_key = st.text_input("API Key", value=default_key, type="password")
    
    c1, c2 = st.columns(2)
    start_d = c1.date_input("開始", value=parse_date("2023-01-01"))
    end_d = c2.date_input("結束", value=parse_date("2023-01-05"))
    
    st.divider()
    success_wait = st.number_input("成功等待(秒)", 60)
    fail_wait = st.number_input("失敗等待(秒)", 20)

col1, col2 = st.columns([1, 1.5])

with col1:
    raw_txt = st.text_area("輸入清單 (一行一個)", height=300, placeholder="9123456\n416000000")
    btn = st.button("🚀 開始執行", use_container_width=True)

with col2:
    status = st.container(border=True)
    p_bar = status.progress(0)
    msg = status.empty()
    logs = st.empty()

async def main_logic():
    ids = [x.strip() for x in raw_txt.split('\n') if x.strip()]
    if not ids or not api_key:
        st.error("請檢查 API Key 與輸入清單")
        return

    temp_root = "temp_download"
    log_hist = []
    success_files = []
    
    for i, vid in enumerate(ids):
        p_bar.progress((i+1)/len(ids))
        msg.markdown(f"### 處理中: `{vid}`")
        
        res = await download_task(api_key, vid, start_d, end_d, temp_root)
        
        if res:
            log_hist.insert(0, f"✅ {vid} 成功")
            # 合併檔案
            target_dir = get_output_dir_path(vid, temp_root)
            if os.path.exists(target_dir):
                combined = []
                header = None
                for f in sorted(os.listdir(target_dir)):
                    if f.endswith(".csv"):
                        with open(os.path.join(target_dir, f), 'r', encoding='utf-8') as cf:
                            reader = csv.reader(cf)
                            try:
                                h = next(reader)
                                if not header: header = h
                                for row in reader: combined.append(row)
                            except: pass
                
                final_path = os.path.join(temp_root, f"{vid}.csv")
                with open(final_path, 'w', encoding='utf-8', newline='') as ff:
                    w = csv.writer(ff)
                    if header: w.writerow(header)
                    w.writerows(combined)
                success_files.append(final_path)
            
            wait = success_wait
        else:
            log_hist.insert(0, f"❌ {vid} 失敗")
            wait = fail_wait
            
        logs.text_area("日誌", "\n".join(log_hist), height=200)
        
        if i < len(ids)-1:
            for t in range(wait, 0, -1):
                msg.markdown(f"⏳ 冷卻中... {t}")
                time.sleep(1)

    msg.success("完成！")
    if success_files:
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, 'w') as z:
            for f in success_files:
                z.write(f, os.path.basename(f))
        st.download_button("📥 下載 ZIP", bio.getvalue(), "tracks.zip", "application/zip", type="primary")

if btn:
    asyncio.run(main_logic())
