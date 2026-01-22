import subprocess
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

class FileManager:
    def __init__(self, las_dir, traj_dir, video_dir, timelapse_ratio=15.0, time_offset=0):
        """
        Inicializa el gestor de archivos.
        timelapse_ratio: Factor de expansión (ej: 15.0 para 30fps @ 0.5s intervalo).
        time_offset: Ajuste horario para el video (ej: -3 para Chile).
        """
        self.dirs = {
            'las': Path(las_dir),
            'traj': Path(traj_dir),
            'video': Path(video_dir)
        }
        self.ratio = timelapse_ratio
        self.offset = time_offset
        self.video_intervals = [] 
        
        # Ejecutar indexación al iniciar
        self._index_files()

    def _get_real_video_metadata(self, video_path):
        """
        Usa ExifTool para extraer fecha de creación y duración exacta.
        """
        try:
            cmd = ['exiftool', '-j', '-n', '-CreateDate', '-Duration', str(video_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if not result.stdout: return None, 0
            
            data = json.loads(result.stdout)[0]
            date_str = data.get('CreateDate')
            if not date_str: return None, 0
            
            # Formato Exif estándar: "YYYY:MM:DD HH:MM:SS"
            start_dt = datetime.strptime(str(date_str)[:19], "%Y:%m:%d %H:%M:%S")
            duration_sec = float(data.get('Duration', 0))

            return start_dt, duration_sec
        except Exception:
            return None, 0

    def _parse_filename_date(self, filename):
        """Parsea fechas formato YYMMDD_HHMMSS del nombre de archivo"""
        try:
            # Busca los primeros 13 caracteres que cumplan el formato
            # Esto ayuda si el nombre es "260115_092245_Trayectoria.csv"
            return datetime.strptime(filename.name[:13], "%y%m%d_%H%M%S")
        except:
            return None

    def _index_files(self):
        # 1. Indexar Videos (Con lógica de Offset y Ratio)
        print(f" Indexando videos (Ratio x{self.ratio} | Offset {self.offset}h)...")
        extensions = ["*.insv", "*.mp4", "*.lrv", "*.INSV", "*.MP4", "*.LRV"]
        found_videos = list(set([f for ext in extensions for f in self.dirs['video'].glob(ext)]))

        for f in found_videos:
            start_dt_utc, duration_file = self._get_real_video_metadata(f)
            
            if start_dt_utc and duration_file > 0:
                # Ajuste de zona horaria y timelapse
                start_dt_local = start_dt_utc + timedelta(hours=self.offset)
                real_duration_seconds = duration_file * self.ratio
                end_dt_local = start_dt_local + timedelta(seconds=real_duration_seconds)
                
                self.video_intervals.append({
                    'path': f,
                    'name': f.name,
                    'start': start_dt_local,
                    'end': end_dt_local,
                    'file_duration': duration_file,
                    'real_duration': real_duration_seconds
                })
        
        self.video_intervals.sort(key=lambda x: x['start'])
        
        # 2. Indexar LAS
        self.las_map = {}
        for f in self.dirs['las'].glob("*.las"):
            dt = self._parse_filename_date(f)
            if dt: self.las_map[f.name] = {'path': f, 'dt': dt}

        # 3. Indexar Trayectorias (CSV)
        self.traj_map = {}
        for f in self.dirs['traj'].glob("*.csv"):
            dt = self._parse_filename_date(f)
            if dt: 
                # Guardamos fecha completa para poder comparar
                key = dt.strftime("%y%m%d_%H%M%S")
                self.traj_map[key] = {'path': f, 'dt': dt, 'name': f.name}

    def get_trajectory_for_las(self, las_name):
        """
        Busca el CSV correspondiente.
        1. Intenta match exacto.
        2. Si falla, busca el archivo más cercano en tiempo del MISMO DÍA.
        """
        dt_las = self._parse_filename_date(Path(las_name))
        if not dt_las: return None

        # Opción 1: Búsqueda Exacta
        key_exact = dt_las.strftime("%y%m%d_%H%M%S")
        if key_exact in self.traj_map:
            return self.traj_map[key_exact]

        # Opción 2: Búsqueda Aproximada (Fuzzy Match)
        print(f"     No hay match exacto para {las_name}. Buscando el más cercano...")
        
        candidates = []
        for key, val in self.traj_map.items():
            # Verificamos que sea el mismo día (YYMMDD)
            if val['dt'].date() == dt_las.date():
                candidates.append(val)
        
        if not candidates:
            return None

        # Encontramos el candidato con la menor diferencia de tiempo
        # Esto elige el 09:22:45 para el LAS de 09:23:37 automáticamente
        best_match = min(candidates, key=lambda x: abs((x['dt'] - dt_las).total_seconds()))
        
        print(f"    Match aproximado encontrado: {best_match['name']} (Diferencia: {abs((best_match['dt'] - dt_las).total_seconds()):.0f}s)")
        
        return best_match

    def find_video_containing_event(self, event_time_local):
        for vid in self.video_intervals:
            if vid['start'] <= event_time_local <= vid['end']:
                return vid 
        return None