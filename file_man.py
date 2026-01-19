import subprocess
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

class FileManager:
    def __init__(self, las_dir, traj_dir, video_dir, timelapse_ratio=15.0):
        """
        Inicializa el gestor de archivos.
        timelapse_ratio: Factor de expansión (ej: 15.0 para 30fps @ 0.5s intervalo).
        """
        self.dirs = {
            'las': Path(las_dir),
            'traj': Path(traj_dir),
            'video': Path(video_dir)
        }
        self.ratio = timelapse_ratio
        self.video_intervals = [] 
        
        # Ejecutar indexación al iniciar
        self._index_files()

    def _get_real_video_metadata(self, video_path):
        """
        Usa ExifTool para extraer fecha de creación y duración exacta.
        Retorna: (datetime_obj, duration_seconds_float)
        """
        try:
            # -n es CRÍTICO: Pide valores numéricos crudos
            cmd = ['exiftool', '-j', '-n', '-CreateDate', '-Duration', str(video_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if not result.stdout: 
                return None, 0
            
            data = json.loads(result.stdout)[0]
            date_str = data.get('CreateDate')
            
            if not date_str: 
                return None, 0
            
            # Formato Exif estándar: "YYYY:MM:DD HH:MM:SS"
            # Tomamos los primeros 19 caracteres para limpiar cualquier zona horaria extra
            start_dt = datetime.strptime(str(date_str)[:19], "%Y:%m:%d %H:%M:%S")
            duration_sec = float(data.get('Duration', 0))

            return start_dt, duration_sec
        except Exception as e:
            # Error silencioso o warning mínimo en producción
            # print(f"⚠️ No se pudo leer metadata de {video_path.name}: {e}")
            return None, 0

    def _parse_filename_date(self, filename):
        """Parsea fechas formato YYMMDD_HHMMSS del nombre de archivo"""
        try:
            return datetime.strptime(filename.name[:13], "%y%m%d_%H%M%S")
        except:
            return None

    def _index_files(self):
        # 1. Indexar Videos
        extensions = ["*.insv", "*.mp4", "*.lrv", "*.INSV", "*.MP4", "*.LRV"]
        # Usamos set para evitar duplicados si hay coincidencia de patrones
        found_videos = list(set([f for ext in extensions for f in self.dirs['video'].glob(ext)]))

        for f in found_videos:
            start_dt, duration_file = self._get_real_video_metadata(f)
            
            if start_dt and duration_file > 0:
                # CÁLCULO CRÍTICO: Duración Real = Duración Archivo * Ratio Timelapse
                real_duration_seconds = duration_file * self.ratio
                end_dt = start_dt + timedelta(seconds=real_duration_seconds)
                
                self.video_intervals.append({
                    'path': f,
                    'name': f.name,
                    'start': start_dt,
                    'end': end_dt,
                    'file_duration': duration_file,
                    'real_duration': real_duration_seconds
                })
        
        # Ordenar videos cronológicamente
        self.video_intervals.sort(key=lambda x: x['start'])
        print(f" FileManager: {len(self.video_intervals)} videos indexados (Ratio x{self.ratio}).")

        # 2. Indexar Nubes (LAS)
        self.las_map = {}
        for f in self.dirs['las'].glob("*.las"):
            dt = self._parse_filename_date(f)
            if dt: self.las_map[f.name] = {'path': f, 'dt': dt}

        # 3. Indexar Trayectorias (CSV)
        self.traj_map = {}
        for f in self.dirs['traj'].glob("*.csv"):
            dt = self._parse_filename_date(f)
            if dt: 
                # Clave de búsqueda: YYMMDD_HHMMSS
                self.traj_map[dt.strftime("%y%m%d_%H%M%S")] = {'path': f, 'dt': dt}

    def get_trajectory_for_las(self, las_name):
        """Busca el CSV con el mismo timestamp que el LAS"""
        dt = self._parse_filename_date(Path(las_name))
        return self.traj_map.get(dt.strftime("%y%m%d_%H%M%S")) if dt else None

    def find_video_containing_event(self, event_time_local):
        """Busca el video donde Start <= Evento <= End"""
        for vid in self.video_intervals:
            if vid['start'] <= event_time_local <= vid['end']:
                return vid 
        return None