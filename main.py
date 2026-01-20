from file_man import FileManager
from sync import SyncEngine
from extractor import FrameExtractor  # <--- [NUEVO IMPORT]
from datetime import datetime, timedelta
import json


# ================= CONFIGURACIÓN =================
LAS_FOLDER = "las/"
TRAJ_FOLDER = "vid/"
VIDEO_FOLDER = "traj/"

FPS = 29.97
TIMELAPSE_RATIO = 15.0 
GPS_TO_VIDEO_OFFSET = 0 

# ================= INPUT (Simulación) =================
alerts_input = [
    {
        "id": "ALERTA_TEST_REAL",
        "source_las": "260114_122451.las", 
        "lat": -33.312307798,
        "lon": -70.768899216,
        "clase": "Vegetacion"
    }
]

def run_pipeline():
    # Inicialización de módulos
    manager = FileManager(LAS_FOLDER, TRAJ_FOLDER, VIDEO_FOLDER, timelapse_ratio=TIMELAPSE_RATIO)
    engine = SyncEngine()
    
    # [NUEVO] Instanciamos el Extractor
    extractor = FrameExtractor(output_folder=OUTPUT_IMG_FOLDER)
    
    results = []

    print(f"🚀 Procesando {len(alerts_input)} alertas...")

    for alert in alerts_input:
        # ... (Lógica de búsqueda de trayectoria igual que antes) ...
        traj_info = manager.get_trajectory_for_las(alert['source_las'])
        if not traj_info:
            results.append({**alert, "status": "ERROR_NO_TRAJ_FILE"})
            continue

        engine.load_trajectory(traj_info['path'])
        geo_match = engine.find_event(alert['lat'], alert['lon'])
        
        if not geo_match:
            results.append({**alert, "status": "ERROR_OUT_OF_BOUNDS"})
            continue

        # ... (Lógica temporal igual que antes) ...
        flight_date = traj_info['dt']
        gps_sod = geo_match['sod']
        event_utc = flight_date.replace(hour=0, minute=0, second=0) + timedelta(seconds=gps_sod)
        event_local = event_utc + timedelta(hours=GPS_TO_VIDEO_OFFSET)

        video_match = manager.find_video_containing_event(event_local)

        if not video_match:
            results.append({**alert, "status": "NO_VIDEO_COVERAGE"})
            continue

        # Cálculo de Frame
        frame, vid_time = engine.calculate_video_frame(
            gps_sod=gps_sod,
            video_start_dt=video_match['start'],
            flight_date_dt=flight_date,
            fps=FPS,
            ratio=TIMELAPSE_RATIO,
            offset_hours=GPS_TO_VIDEO_OFFSET
        )

        # ====================================================
        # [NUEVO] EXTRACCIÓN DE LA IMAGEN
        # ====================================================
        print(f"   📸 Extrayendo frame {frame} de {video_match['name']}...")
        
        image_path = extractor.extract(
            video_path=video_match['path'], 
            frame_number=frame, 
            alert_id=alert['id']
        )
        
        status_final = "SUCCESS_WITH_IMAGE" if image_path else "SUCCESS_NO_IMAGE"

        results.append({
            "alert_id": alert['id'],
            "status": status_final,
            "video_file": video_match['name'],
            "frame": frame,
            "seconds_in_video": round(vid_time, 2),
            "image_path": image_path, # <--- Agregamos la ruta al JSON
            "dist_traj_m": round(geo_match['dist_m'], 2)
        })

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    run_pipeline()