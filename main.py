from file_man import FileManager
from sync import SyncEngine
from extract import FrameExtractor # Asegúrate de que el archivo se llame extractor.py
from datetime import datetime, timedelta
import json
import os

# ================= CONFIGURACIÓN =================
LAS_FOLDER = "las/"
TRAJ_FOLDER = "traj/" 
VIDEO_FOLDER = "vid/"
OUTPUT_IMG_FOLDER = "data/"

FPS = 29.97
TIMELAPSE_RATIO = 15.0 
GPS_TO_VIDEO_OFFSET = -3 # (UTC a Local)

# ================= INPUT =================
alerts_input = [
    # CASO: Tienes el GPS Time del punto (CloudCompare)
    {
        "id": "Punto_CC_1351640",
        "source_las": "260115_092337_ex.las", 
        "gps_time": 45040.777344, 
        "clase": "Directo_GPS"
    }
]

def run_pipeline():
    # Inicialización
    manager = FileManager(LAS_FOLDER, TRAJ_FOLDER, VIDEO_FOLDER, 
                          timelapse_ratio=TIMELAPSE_RATIO, 
                          time_offset=GPS_TO_VIDEO_OFFSET)
    engine = SyncEngine()
    
    # El extractor nuevo ya no necesita configurarse, solo instanciarse
    extractor = FrameExtractor(output_folder=OUTPUT_IMG_FOLDER)
    results = []

    # --- DIAGNÓSTICO DE TRAYECTORIAS (Para evitar nulls) ---
    print("\n --- DIAGNÓSTICO DE ARCHIVOS CSV ---")
    if not manager.traj_map:
        print("  ALERTA: No se detectó ningún archivo CSV válido en 'traj/'.")
    else:
        print(f" Se encontraron {len(manager.traj_map)} trayectorias indexadas.")
    print("--------------------------------------\n")

    print(f" Procesando {len(alerts_input)} alertas...")

    for alert in alerts_input:
        # 1. Obtener Fecha Base del Vuelo
        dummy_path = manager.dirs['las'] / alert['source_las']
        flight_date = manager._parse_filename_date(dummy_path)
        
        if not flight_date:
            print(f" Skip: No se pudo extraer fecha de {alert['source_las']}")
            continue

        # 2. Cargar Trayectoria y Buscar Datos del Vehículo
        traj_info = manager.get_trajectory_for_las(alert['source_las'])
        traj_data = {}
        gps_sod_final = 0.0

        if traj_info:
            print(f" Usando trayectoria: {traj_info['name']}")
            engine.load_trajectory(traj_info['path'])
            
            if 'gps_time' in alert:
                match = engine.find_event_temporal(alert['gps_time'])
                if match:
                    gps_sod_final = alert['gps_time']
                    traj_data = match 
            elif 'lat' in alert:
                match = engine.find_event_spatial(alert['lat'], alert['lon'])
                if match:
                    gps_sod_final = match['sod']
                    traj_data = match
        else:
            print(f"  ADVERTENCIA: No hay CSV para {alert['source_las']}. Se procesará solo video.")
            if 'gps_time' in alert:
                gps_sod_final = alert['gps_time']
            else:
                results.append({**alert, "status": "ERROR_NO_TRAJ_DATA"})
                continue

        # 3. Calcular Timestamp Completo
        event_dt_utc = flight_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=gps_sod_final)
        event_dt_local = event_dt_utc + timedelta(hours=GPS_TO_VIDEO_OFFSET)

        # 4. Buscar Video
        video_match = manager.find_video_containing_event(event_dt_local)
        
        if not video_match:
            results.append({
                "alert_id": alert['id'],
                "status": "NO_VIDEO_COVERAGE",
                "timestamp_data": {
                    "utc": event_dt_utc.isoformat(),
                    "local": event_dt_local.isoformat()
                }
            })
            continue

        # 5. Calcular Frame y Tiempo
        frame, vid_time, _ = engine.calculate_video_frame(
            gps_sod=gps_sod_final,
            video_start_dt=video_match['start'],
            flight_date_dt=flight_date,
            fps=FPS,
            ratio=TIMELAPSE_RATIO,
            offset_hours=GPS_TO_VIDEO_OFFSET
        )

        # 6. Extraer Evidencia (USANDO vid_time AHORA)
        print(f"   {alert['id']} -> {video_match['name']} [Seg: {vid_time:.2f}]")
        
        # CAMBIO CRÍTICO: Pasamos 'vid_time' (segundos), no frame number
        image_paths_dict = extractor.extract(video_match['path'], vid_time, alert['id'])

        status_final = "SUCCESS" if image_paths_dict else "ERROR_EXTRACT"

        # 7. Construir JSON Final
        results.append({
            "alert_id": alert['id'],
            "status": status_final,
            
            "timestamp_data": {
                "date": flight_date.strftime("%Y-%m-%d"),
                "gps_sod": gps_sod_final,
                "utc_time": event_dt_utc.isoformat(),
                "local_time": event_dt_local.isoformat(),
                "readable": event_dt_local.strftime("%d/%m/%Y %H:%M:%S.%f")
            },
            
            "vehicle_position": {
                "lat": traj_data.get('lat_traj'),
                "lon": traj_data.get('lon_traj'),
                "yaw": traj_data.get('yaw'),
                "match_source": traj_data.get('match_type', 'none')
            },

            "evidence": {
                "video_file": video_match['name'],
                "frame_estimated": frame,
                "video_second": round(vid_time, 2),
                # Ahora guardamos el diccionario con front/back
                "images": image_paths_dict 
            }
        })

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    run_pipeline()