from file_man import FileManager
from sync import SyncEngine
from extract import FrameExtractor  # <--- [NUEVO IMPORT]
from datetime import datetime, timedelta
import json


# ================= CONFIGURACIÓN =================
LAS_FOLDER = "las/"
TRAJ_FOLDER = "traj/"
VIDEO_FOLDER = "vid/"
OUTPUT_IMG_FOLDER = "data/"
FPS = 29.97
TIMELAPSE_RATIO = 15.0 
GPS_TO_VIDEO_OFFSET = -3 

# ================= INPUT HÍBRIDO =================
alerts_input = [
    # CASO 1: TU PUNTO EXACTO DE CLOUDCOMPARE (Por Tiempo)
    {
        "id": "Punto_CC_1351640",
        "source_las": "260115_092337_ex.las", # Necesario para saber la FECHA (Año-Mes-Dia)
        "gps_time": 45040.777344,             # <--- EL VALOR DE TU PANTALLAZO
        "clase": "Directo_GPS"
    },
    
    # CASO 2: ALERTA ANTIGUA (Por Coordenada)
    # {
    #     "id": "ALERTA_GPS_LATLON",
    #     "source_las": "260114_122451.las", 
    #     "lat": -33.312307,
    #     "lon": -70.768899,
    #     "clase": "Vegetacion"
    # }
]

def run_pipeline():
    # AQUI ESTA LA MAGIA: Le pasamos el offset al manager también
    manager = FileManager(
        LAS_FOLDER, TRAJ_FOLDER, VIDEO_FOLDER, 
        timelapse_ratio=TIMELAPSE_RATIO,
        time_offset=GPS_TO_VIDEO_OFFSET 
    )
    engine = SyncEngine()
    extractor = FrameExtractor(output_folder=OUTPUT_IMG_FOLDER)
    results = []

    print(f"🚀 Procesando {len(alerts_input)} alertas...")

    for alert in alerts_input:
        dummy_path = manager.dirs['las'] / alert['source_las']
        flight_date = manager._parse_filename_date(dummy_path)
        
        if not flight_date: continue

        gps_sod = 0.0
        match_metadata = {}

        if 'gps_time' in alert:
            gps_sod = alert['gps_time']
            match_metadata = {"method": "direct_gps_time"}
        else:
            # Lógica espacial (omitida por brevedad, usa la anterior si la necesitas)
            pass

        # Calculamos Hora Evento Local
        event_utc = flight_date.replace(hour=0, minute=0, second=0) + timedelta(seconds=gps_sod)
        event_local = event_utc + timedelta(hours=GPS_TO_VIDEO_OFFSET)

        print(f"📍 Buscando evento en: {event_local.time()}")

        video_match = manager.find_video_containing_event(event_local)

        if not video_match:
            print(f"   ⚠️ Sin cobertura para {event_local.time()}")
            results.append({**alert, "status": "NO_VIDEO_COVERAGE"})
            continue

        frame, vid_time = engine.calculate_video_frame(
            gps_sod=gps_sod,
            video_start_dt=video_match['start'],
            flight_date_dt=flight_date,
            fps=FPS,
            ratio=TIMELAPSE_RATIO,
            # OJO: Como ya corregimos el video al cargarlo, el offset aqui debe ser 0 
            # para calcular la diferencia relativa, O pasamos fechas locales.
            # Ajuste de calculate_video_frame simplificado abajo:
            offset_hours=0 
        )
        
        # Recalculo manual simple aquí para asegurar consistencia Local vs Local
        delta_seconds = (event_local - video_match['start']).total_seconds()
        vid_time = delta_seconds / TIMELAPSE_RATIO
        frame = int(vid_time * FPS)

        print(f"   ✅ MATCH! Frame {frame}")
        image_path = extractor.extract(video_match['path'], frame, alert['id'])
        
        results.append({
            "alert_id": alert['id'],
            "status": "SUCCESS" if image_path else "SUCCESS_NO_IMG",
            "video_file": video_match['name'],
            "frame": frame,
            "seconds_in_video": round(vid_time, 2),
            "image_path": image_path,
            **match_metadata
        })

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    run_pipeline()