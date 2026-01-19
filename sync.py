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
        """
        Carga la trayectoria de forma silenciosa.
        """
        # Evitar recargar si ya es el mismo archivo
        if str(csv_path) == str(self.current_traj_path):
            return

        # Cargar CSV
        self.df = pd.read_csv(csv_path, sep=',') 
        
        # Mapeo de columnas
        cols = {'riegl.pof_latitude': 'lat', 'riegl.pof_longitude': 'lon', 
                'riegl.pof_timestamp': 'sod', 'riegl.pof_yaw': 'yaw'}
        self.df.rename(columns=cols, inplace=True)
        
        # Conversión UTM y KDTree (Vectorizado = Rápido y sin prints)
        ux, uy = self.proj(self.df['lon'].values, self.df['lat'].values)
        self.df['x_utm'], self.df['y_utm'] = ux, uy
        self.tree = KDTree(np.c_[ux, uy])
        
        self.current_traj_path = csv_path

    def find_event(self, lat, lon):
        if self.tree is None: return None
        tx, ty = self.proj(lon, lat)
        dist, idx = self.tree.query([tx, ty])
        row = self.df.iloc[idx]
        return {
            'dist_m': dist,
            'sod': row['sod'], 
            'yaw': row['yaw']
        }

    @staticmethod
    def calculate_video_frame(gps_sod, video_start_dt, flight_date_dt, fps, ratio, offset_hours):
        event_utc = flight_date_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=gps_sod)
        event_local = event_utc + timedelta(hours=offset_hours)
        delta_real = (event_local - video_start_dt).total_seconds()
        
        frame = int((delta_real / ratio) * fps)
        video_time = delta_real / ratio
        
        return frame, video_time