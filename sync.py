import pandas as pd
import numpy as np
from scipy.spatial import KDTree
from datetime import datetime, timedelta
from pyproj import Proj

class SyncEngine:
    def __init__(self):
        # Proyección UTM Zona 19S (Chile).
        self.proj = Proj("+proj=utm +zone=19 +south +ellps=WGS84 +datum=WGS84 +units=m +no_defs")
        self.current_traj_path = None
        self.df = None
        self.tree = None

    def load_trajectory(self, csv_path):
        """Carga la trayectoria y prepara el KDTree espacial."""
        if str(csv_path) == str(self.current_traj_path):
            return

        # Cargar CSV
        self.df = pd.read_csv(csv_path, sep=',') 
        
        # Mapeo de columnas
        cols = {'riegl.pof_latitude': 'lat', 'riegl.pof_longitude': 'lon', 
                'riegl.pof_timestamp': 'sod', 'riegl.pof_yaw': 'yaw'}
        self.df.rename(columns=cols, inplace=True)
        
        # Ordenamos por tiempo para permitir búsqueda binaria
        self.df = self.df.sort_values('sod').reset_index(drop=True)

        # Preparar búsqueda espacial (KDTree)
        ux, uy = self.proj(self.df['lon'].values, self.df['lat'].values)
        self.df['x_utm'], self.df['y_utm'] = ux, uy
        self.tree = KDTree(np.c_[ux, uy])
        
        self.current_traj_path = csv_path

    def find_event_spatial(self, lat, lon):
        """Busca el punto más cercano espacialmente (Lat/Lon input)."""
        if self.tree is None: return None
        tx, ty = self.proj(lon, lat)
        dist, idx = self.tree.query([tx, ty])
        row = self.df.iloc[idx]
        return {
            'match_type': 'space',
            'dist_diff_m': float(dist),
            'sod': float(row['sod']), 
            'lat_traj': float(row['lat']),
            'lon_traj': float(row['lon']),
            'yaw': float(row['yaw'])
        }

    def find_event_temporal(self, target_sod):
        """Busca el punto más cercano temporalmente (GPS Time input)."""
        if self.df is None: return None
        
        # Búsqueda Binaria (Ultra rápida)
        # searchsorted busca dónde debería insertarse el target_sod para mantener el orden
        idx = np.searchsorted(self.df['sod'].values, target_sod)
        
        # Ajuste de bordes (si se sale del rango)
        if idx >= len(self.df): idx = len(self.df) - 1
        if idx < 0: idx = 0

        # Comparar con el índice anterior para ver cuál está más cerca realmente
        if idx > 0:
            diff_curr = abs(self.df.iloc[idx]['sod'] - target_sod)
            diff_prev = abs(self.df.iloc[idx-1]['sod'] - target_sod)
            if diff_prev < diff_curr:
                idx = idx - 1

        row = self.df.iloc[idx]
        
        return {
            'match_type': 'time',
            'time_diff_s': float(abs(row['sod'] - target_sod)),
            'sod': float(row['sod']),
            'lat_traj': float(row['lat']),
            'lon_traj': float(row['lon']),
            'yaw': float(row['yaw'])
        }

    @staticmethod
    def calculate_video_frame(gps_sod, video_start_dt, flight_date_dt, fps, ratio, offset_hours):
        # 1. UTC Absoluto
        event_utc = flight_date_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=gps_sod)
        
        # 2. Local Video Time (Ya ajustado con offset en el FileManager, así que aquí comparamos con Local)
        # IMPORTANTE: Si video_start_dt ya tiene el offset aplicado (en file_man), 
        # entonces event_utc debe convertirse a local también.
        event_local = event_utc + timedelta(hours=offset_hours)
        
        delta_real = (event_local - video_start_dt).total_seconds()
        
        frame = int((delta_real / ratio) * fps)
        video_time = delta_real / ratio
        
        return frame, video_time, str(event_local)