import cv2
import os
from pathlib import Path

class FrameExtractor:
    def __init__(self, output_folder="./output_images"):
        """
        Inicializa el extractor de evidencias.
        :param output_folder: Directorio donde se guardarán los JPGs.
        """
        self.output_dir = Path(output_folder)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"📷 Extractor iniciado. Guardando en: {self.output_dir.resolve()}")

    def extract(self, video_path, frame_number, alert_id):
        """
        Abre el video, busca el frame y guarda la imagen.
        Retorna la ruta de la imagen guardada o None si falló.
        """
        video_str = str(video_path)
        
        # 1. Validar existencia
        if not os.path.exists(video_str):
            print(f"   ❌ Error IO: No encuentro el video {video_str}")
            return None

        # 2. Inicializar Captura
        cap = cv2.VideoCapture(video_str)
        
        if not cap.isOpened():
            print(f"   ❌ Error CV2: No se pudo abrir el codec para {video_path.name}")
            return None

        try:
            # 3. Seeking Eficiente (O(1) en la mayoría de codecs modernos)
            # Seteamos la posición del puntero de lectura al frame deseado
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            # 4. Decodificar Frame
            ret, image = cap.read()
            
            if not ret:
                print(f"   ❌ Error Read: No se pudo leer el frame {frame_number} (¿Fin de archivo?)")
                return None

            # 5. Construir nombre de archivo único
            # Ejemplo: ALERTA_001_frame_450.jpg
            filename = f"{alert_id}_frm{frame_number}.jpg"
            save_path = self.output_dir / filename

            # 6. Guardar a Disco
            cv2.imwrite(str(save_path), image)
            return str(save_path)

        except Exception as e:
            print(f"   ❌ Excepción no controlada en extracción: {e}")
            return None
            
        finally:
            # 7. Liberar Recurso (Crítico para no saturar RAM/File handles)
            cap.release()