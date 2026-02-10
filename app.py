import streamlit as st
import asyncio
import os
import shutil
import time
import zipfile
import io
import csv
from date_utils import parse_date
from download_api import download_vessel_track_data
from path_utils import get_output_dir_path

# --- 頁面設定 ---
st.set_page_config(page_title="船舶軌跡下載器", layout="wide")
st.title("🚢 船舶軌跡批次下載 (MMSI / IMO)")

# --- 側邊欄：設定 ---
with st.sidebar:
    st.header("1. 設定參數")
    default_key = os.getenv("MARINE_TRAFFIC_API_KEY", "")
    api_key = st.text_input("API Key", value=default_key, type="password")
    
    col1, col2 = st.columns(2)
    start_date = col1.date_input("開始日期", value=parse_date("2023-01-01"))
    end_date = col2.date_input("結束日期", value=parse_date("2023-01-05"))
    
    st.divider()
    st.header("2. 下載策略")
    success_wait = st.number_input("成功後等待 (秒)", value=60, min_value=0)
    fail_wait = st.number_input("失敗後等待 (秒)", value=20, min_value=0)

# --- 主畫面：輸入與輸出 ---
col_left, col_right = st.columns([1, 1.5])

with col_left:
    st.subheader("輸入清單")
    raw_input = st.text_area("請輸入 MMSI 或 IMO (一行一個)", height=300, 
                            placeholder="9123456\n416000000")
    start_btn = st.button("🚀 開始批次下載", use_container_width=True)

with col_right:
    st.subheader("執行進度")
    status_box = st.container(border=True)
    progress_bar = status_box.progress(0)
    status_text = status_box.empty()
    log_area = st.empty()

# --- 核心邏輯 ---
async def run_batch_download():
    # 1. 準備資料
    id_list = [line.strip() for line in raw_input.split('\n') if line.strip()]
    if not id_list:
        st.error("❌ 請輸入至少一組 MMSI 或 IMO")
        return

    if not api_key:
        st.error("❌ 請輸入 API Key")
        return

    temp_root = "./temp_web_download"
    # 清空並重建暫存目錄
    if os.path.exists(temp_root):
        shutil.rmtree(temp_root)
    os.makedirs(temp_root, exist_ok=True)

    total_ships = len(id_list)
    success_files = [] # 紀錄成功下載的檔案路徑
    logs = []

    # 2. 開始迴圈
    for idx, vessel_id in enumerate(id_list):
        current = idx + 1
        progress_bar.progress(current / total_ships)
        status_text.markdown(f"### 🔄 正在處理 ({current}/{total_ships}): `{vessel_id}`")
        
        # 顯示 Log
        logs.insert(0, f"[{time.strftime('%H:%M:%S')}] 開始下載: {vessel_id}")
        log_area.text_area("執行日誌", "\n".join(logs), height=250)

        # 呼叫下載 API
        is_success = await download_vessel_track_data(
            api_key, vessel_id, start_date, end_date, temp_root
        )

        if is_success:
            logs.insert(0, f"✅ {vessel_id} 下載成功！")
            
            # --- 自動合併 CSV (將分段檔案合為一個) ---
            target_dir = get_output_dir_path(vessel_id, temp_root)
            if os.path.exists(target_dir):
                # 找出所有分段 csv
                chunk_files = sorted([f for f in os.listdir(target_dir) if f.endswith(".csv")])
                if chunk_files:
                    combined_data = []
                    header = None
                    
                    for f in chunk_files:
                        with open(os.path.join(target_dir, f), 'r', encoding='utf-8') as cf:
                            reader = csv.reader(cf)
                            try:
                                h = next(reader)
                                if not header: header = h
                                for row in reader: combined_data.append(row)
                            except StopIteration: pass
                    
                    # 存成單一檔案到 temp_root 根目錄，方便打包
                    final_filename = f"track_{vessel_id}.csv"
                    final_path = os.path.join(temp_root, final_filename)
                    with open(final_path, 'w', encoding='utf-8', newline='') as f:
                        writer = csv.writer(f)
                        if header: writer.writerow(header)
                        writer.writerows(combined_data)
                    
                    success_files.append(final_path)
            # ----------------------------------------

            wait_time = success_wait
        else:
            logs.insert(0, f"⚠️ {vessel_id} 下載失敗或無資料。")
            wait_time = fail_wait

        log_area.text_area("執行日誌", "\n".join(logs), height=250)

        # 等待機制 (如果是最後一艘就不等)
        if current < total_ships:
            for t in range(wait_time, 0, -1):
                status_text.markdown(f"### ⏳ 冷卻中... 剩餘 {t} 秒 (下一艘: {id_list[idx+1]})")
                time.sleep(1)

    # 3. 全部完成，打包 ZIP
    status_text.success("🎉 所有任務執行完畢！")
    
    if success_files:
        # 建立 ZIP 檔於記憶體中
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for file_path in success_files:
                # 把檔案加入 zip，並只保留檔名 (不含路徑)
                zf.write(file_path, arcname=os.path.basename(file_path))
        
        # 顯示下載按鈕
        st.balloons()
        st.download_button(
            label=f"📥 下載 ZIP 壓縮檔 (共 {len(success_files)} 個檔案)",
            data=zip_buffer.getvalue(),
            file_name=f"vessel_tracks_{date.today()}.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )
    else:
        st.warning("沒有成功下載任何檔案。")

# 啟動異步任務
if start_btn:
    asyncio.run(run_batch_download())