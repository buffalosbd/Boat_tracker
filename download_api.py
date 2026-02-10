import os
import shutil
import httpx
import asyncio
from datetime import date
from datetime import timedelta
from date_utils import validate_dates
from path_utils import get_output_dir_path

async def fetch_vessel_track(
    api_key: str,
    vessel_id: str,
    from_date: date,
    to_date: date,
    protocol: str = "csv",
    version: int = 3,
    *,
    output_dir: str,
) -> bool:
    """
    下載船舶軌跡，自動判斷 MMSI (9碼) 或 IMO (7碼)。
    """
    base_url = f"https://services.marinetraffic.com/api/exportvesseltrack/{api_key}"

    # --- 自動判斷邏輯 ---
    vessel_id = str(vessel_id).strip()
    if len(vessel_id) == 9:
        id_param = "MMSI"
    elif len(vessel_id) == 7:
        id_param = "imo"
    else:
        print(f"Error: ID {vessel_id} 長度不正確 (需為 9 碼 MMSI 或 7 碼 IMO)")
        return False

    params = {
        "v": version,
        "fromdate": str(from_date),
        "todate": str(to_date),
        id_param: vessel_id,  # 動態參數
        "protocol": protocol,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()

            # 檔名使用 vessel_id
            filename = f"vessel_track_{vessel_id}_{from_date}_{to_date}.{protocol}"
            
            # 確保目錄存在
            os.makedirs(output_dir, exist_ok=True)
            
            with open(f"{output_dir}/{filename}", "wb") as f:
                f.write(response.content)

            return True

    except Exception as e:
        print(f"下載失敗 ({vessel_id}): {e}")
        return False

async def download_vessel_track_data(
    api_key: str, vessel_id: str, start_date: date, end_date: date, temp_dir: str
) -> bool:
    """
    主下載函數，處理日期切分邏輯
    """
    res = validate_dates(start_date, end_date)
    if not (isinstance(res, tuple) and res[0] == "正確"):
        return False

    days = res[1]
    
    # 設定存檔路徑
    output_dir = get_output_dir_path(mmsi=vessel_id, temp_dir=temp_dir)
    
    # 清空舊資料以防混淆
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 邏輯：如果不超過 180 天，直接下載
    if days <= 180:
        return await fetch_vessel_track(
            api_key, vessel_id, start_date, end_date, output_dir=output_dir
        )
    else:
        # 超過 180 天，切分區段
        current_start = start_date
        all_success = True
        while current_start < end_date:
            current_end = current_start + timedelta(days=180)
            if current_end > end_date:
                current_end = end_date

            res = await fetch_vessel_track(
                api_key, vessel_id, current_start, current_end, output_dir=output_dir
            )
            
            if not res:
                all_success = False # 只要有一段失敗就算失敗

            current_start = current_end + timedelta(days=1)
            
            if current_start < end_date:
                await asyncio.sleep(60) # 切分片段間的休息
                
        return all_success