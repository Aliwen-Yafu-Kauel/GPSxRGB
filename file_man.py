import subprocess
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

class FileManager:
    def __init__(self, las_dir, traj_dir, video_dir, timelapse_ratio=15.0, time_offset=0):
        """
        time_offset: Ajuste horario para el video (ej: -3 para Chile).
        """
        self.dirs = {
            'las': Path(las_dir),
            'traj': Path(traj_dir),
            'video': Path(video_dir)
        }
        self.ratio = timelapse_ratio
        self.offset = time_offset  # <--- NUEVO
        self.video_intervals = [] 
        self._index_files()

    def _get_real_video_metadata(self, video_path):
        try:
            cmd = ['exiftool', '-j', '-n', '-CreateDate', '-Duration', str(video_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if not result.stdout: return None, 0
            
            data = json.loads(result.stdout)[0]
            date_str = data.get('CreateDate')
            if not date_str: return None, 0
            
            # Hora UTC cruda de la cámara
            start_dt = datetime.strptime(str(date_str)[:19], "%Y:%m:%d %H:%M:%S")
            duration_sec = float(data.get('Duration', 0))

            return start_dt, duration_sec
        except Exception:
            return None, 0

    def _parse_filename_date(self, filename):
        try:
            return datetime.strptime(filename.name[:13], "%y%m%d_%H%M%S")
        except:
            return None

    def _index_files(self):
        print(f"📂 Indexando videos (Ratio x{self.ratio} | Offset {self.offset}h)...")
        extensions = ["*.insv", "*.mp4", "*.lrv", "*.INSV", "*.MP4", "*.LRV"]
        found_videos = list(set([f for ext in extensions for f in self.dirs['video'].glob(ext)]))

        for f in found_videos:
            start_dt_utc, duration_file = self._get_real_video_metadata(f)
            
            if start_dt_utc and duration_file > 0:
                # 1. APLICAR OFFSET AL VIDEO (UTC -> LOCAL)
                start_dt_local = start_dt_utc + timedelta(hours=self.offset)

                # 2. CALCULAR DURACIÓN REAL
                real_duration_seconds = duration_file * self.ratio
                end_dt_local = start_dt_local + timedelta(seconds=real_duration_seconds)
                
                self.video_intervals.append({
                    'path': f,
                    'name': f.name,
                    'start': start_dt_local, # Guardamos la hora corregida
                    'end': end_dt_local,
                    'file_duration': duration_file,
                    'real_duration': real_duration_seconds
                })
        
        self.video_intervals.sort(key=lambda x: x['start'])
        # Indexar LAS y TRAJ (igual que antes)
        self.las_map = {}
        for f in self.dirs['las'].glob("*.las"):
            dt = self._parse_filename_date(f)
            if dt: self.las_map[f.name] = {'path': f, 'dt': dt}

        self.traj_map = {}
        for f in self.dirs['traj'].glob("*.csv"):
            dt = self._parse_filename_date(f)
            if dt: self.traj_map[dt.strftime("%y%m%d_%H%M%S")] = {'path': f, 'dt': dt}

    def get_trajectory_for_las(self, las_name):
        dt = self._parse_filename_date(Path(las_name))
        return self.traj_map.get(dt.strftime("%y%m%d_%H%M%S")) if dt else None

    def find_video_containing_event(self, event_time_local):
        for vid in self.video_intervals:
            if vid['start'] <= event_time_local <= vid['end']:
                return vid 
        return None