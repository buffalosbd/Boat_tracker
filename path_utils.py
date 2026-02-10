def get_output_dir_path(mmsi: str, temp_dir: str) -> str:
    return f"{temp_dir}/vessel_track_{mmsi}"


def final_result_dir_path(mmsi: str, results_dir: str) -> str:
    return f"{results_dir}/vessel_track_{mmsi}"
