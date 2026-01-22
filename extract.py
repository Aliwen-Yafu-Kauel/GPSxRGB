import ffmpeg
import os
from pathlib import Path

class FrameExtractor:
    def __init__(self, output_folder="./output_images"):
        self.output_dir = Path(output_folder)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f" Extractor FFmpeg (Resolución Dinámica) listo. Salida: {self.output_dir.resolve()}")

    def _get_video_resolution(self, video_path):
        """
        Usa ffprobe para obtener las dimensiones reales del video.
        Retorna: (width, height)
        """
        try:
            probe = ffmpeg.probe(str(video_path))
            video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            if video_stream is None:
                return None, None
            
            width = int(video_stream['width'])
            height = int(video_stream['height'])
            return width, height
        except ffmpeg.Error as e:
            print(f" No se pudo leer metadata de {video_path}: {e}")
            return None, None

    def extract(self, video_path, timestamp, alert_id):
        video_str = str(video_path)
        if not os.path.exists(video_str):
            print(f" Video no encontrado: {video_str}")
            return None

        # 1. OBTENER RESOLUCIÓN NATIVA
        raw_w, raw_h = self._get_video_resolution(video_str)
        
        if not raw_w or not raw_h:
            print(" Falló la detección de resolución. Usando fallback 1920x1080.")
            out_dim = 1080 # Fallback
        else:
            # LÓGICA DINÁMICA:
            # En Dual Fisheye, el video es el doble de ancho que de alto (Ej: 5760x2880).
            # La resolución máxima de un solo "ojo" está limitada por la altura.
            # Por tanto, usaremos la altura nativa como la dimensión de nuestra imagen cuadrada.
            out_dim = raw_h
            print(f"   Input: {raw_w}x{raw_h} -> Output Dinámico: {out_dim}x{out_dim}px")

        path_front = self.output_dir / f"{alert_id}_FRONT.jpg"
        path_back = self.output_dir / f"{alert_id}_BACK.jpg"

        try:
            stream = ffmpeg.input(video_str, ss=timestamp)

            common_params = {
                'input': 'dfisheye',
                'output': 'rectilinear',
                
                # FOV Input: Insta360 suele usar 190-200 grados por lente
                'ih_fov': 195, 
                'iv_fov': 195,
                
                # FOV Output: 150° para ver "casi todo" sin romper demasiado la imagen
                'h_fov': 150,
                'v_fov': 150, 
                
                # RESOLUCIÓN DINÁMICA APLICADA
                'w': out_dim,
                'h': out_dim,
            }

            # Vista FRONTAL
            v1 = stream.filter('v360', yaw=0, **common_params)
            
            # Vista TRASERA
            v2 = stream.filter('v360', yaw=180, pitch=0, **common_params)

            # Ejecutar (q=1 máxima calidad JPG)
            # Usamos quiet=True para no ensuciar la consola, a menos que haya error
            ffmpeg.output(v1, str(path_front), vframes=1, q=1).run(overwrite_output=True, quiet=True)
            ffmpeg.output(v2, str(path_back), vframes=1, q=1).run(overwrite_output=True, quiet=True)

            return {"front": str(path_front), "back": str(path_back)}

        except ffmpeg.Error as e:
            print(f" Error FFmpeg: {e.stderr.decode('utf8') if e.stderr else str(e)}")
            return None
        except Exception as e:
            print(f" Error Python: {e}")
            return None