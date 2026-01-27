import laspy
import numpy as np
import pandas as pd
import json
import gc # Garbage Collector para forzar limpieza de RAM
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN

# --- CONFIGURACIÓN ---
CONFIG = {
    "CLASE_CABLE": [4],
    "CLASE_VEG": [2],
    "RADIO_ESFERA": 3.0,
    "CLUSTER_EPS": 4.0,
    "CLUSTER_MIN_SAMPLES": 5,
    "INPUT_FILE": "las/clas_260115_092337_010.las", # <--- CAMBIA ESTO POR TU ARCHIVO
    "OUTPUT_JSON": "alertas_detectadas.json",
    "CHUNK_SIZE": 500_000  # Procesar de a 1 millón de puntos por vez
}

def generar_alertas_streaming(input_path, output_path):
    print(f"--> Iniciando modo 'Memory Safe' para: {input_path}")
    
    # ---------------------------------------------------------
    # FASE 1: EXTRACCIÓN DE CABLES (Mapa de referencia)
    # ---------------------------------------------------------
    print("--> [FASE 1/3] Extrayendo cables (Pasada rápida)...")
    
    puntos_cable_lista = []
    
    # Abrimos el archivo en modo lectura (sin cargarlo todo)
    with laspy.open(input_path) as fh:
        # Iteramos por trozos
        for chunk in fh.chunk_iterator(CONFIG["CHUNK_SIZE"]):
            # Filtramos solo cables en este trozo
            mask_cable = np.isin(chunk.classification, CONFIG["CLASE_CABLE"])
            
            if np.any(mask_cable):
                # Extraemos XYZ de los cables
                coords = np.vstack((
                    chunk.x[mask_cable], 
                    chunk.y[mask_cable], 
                    chunk.z[mask_cable]
                )).transpose()
                puntos_cable_lista.append(coords)
            
            # Liberar memoria explícitamente
            del chunk
            del mask_cable

    if not puntos_cable_lista:
        print("ERROR: No se encontraron cables en todo el archivo.")
        return

    # Consolidamos todos los cables en un solo array
    data_cable = np.vstack(puntos_cable_lista)
    print(f"    Cables cargados en RAM: {len(data_cable)} puntos.")
    
    # Limpiamos la lista temporal para liberar RAM
    del puntos_cable_lista
    gc.collect()

    # Construimos el KD-Tree (Esto es rápido y ligero)
    print("    Construyendo índice espacial (KD-Tree)...")
    tree_cable = cKDTree(data_cable)
    
    # Ya no necesitamos los puntos brutos del cable, solo el árbol
    del data_cable
    gc.collect()

    # ---------------------------------------------------------
    # FASE 2: BARRIDO DE VEGETACIÓN (Streaming)
    # ---------------------------------------------------------
    print("--> [FASE 2/3] Escaneando vegetación por trozos...")
    
    conflictos_acumulados = []
    
    with laspy.open(input_path) as fh:
        count_chunk = 0
        total_puntos_veg = 0
        
        for chunk in fh.chunk_iterator(CONFIG["CHUNK_SIZE"]):
            count_chunk += 1
            # print(f"    Procesando chunk #{count_chunk}...", end='\r')
            
            # Filtramos Veg en este trozo
            mask_veg = np.isin(chunk.classification, CONFIG["CLASE_VEG"])
            
            if not np.any(mask_veg):
                continue

            # Preparamos datos Veg del trozo actual
            # OJO: Necesitamos manejar el tiempo si existe
            try:
                gps_time = chunk.gps_time[mask_veg]
            except AttributeError:
                gps_time = np.zeros(np.sum(mask_veg))

            veg_xyz = np.vstack((
                chunk.x[mask_veg], 
                chunk.y[mask_veg], 
                chunk.z[mask_veg]
            )).transpose()
            
            # Consultamos al KD-Tree (Cables) con este trozo de Vegetación
            # distance_upper_bound retorna infinito si no encuentra nada cerca
            distancias, _ = tree_cable.query(veg_xyz, distance_upper_bound=CONFIG["RADIO_ESFERA"], workers=-1)
            
            # Filtramos los positivos
            indices_conflicto = np.where(distancias <= CONFIG["RADIO_ESFERA"])[0]
            
            if len(indices_conflicto) > 0:
                # Recuperamos los datos completos de los puntos en conflicto
                xyz_conflicto = veg_xyz[indices_conflicto]
                t_conflicto = gps_time[indices_conflicto]
                
                # Juntamos todo (X, Y, Z, Time)
                bloque_conflicto = np.column_stack((xyz_conflicto, t_conflicto))
                conflictos_acumulados.append(bloque_conflicto)
            
            total_puntos_veg += len(veg_xyz)
            
            # Limpieza crítica por iteración
            del chunk, mask_veg, veg_xyz, distancias
    
    print(f"\n    Vegetación analizada: {total_puntos_veg} puntos.")
    
    if not conflictos_acumulados:
        print("RESULTADO: 0 Alertas detectadas.")
        return

    # Consolidamos todos los conflictos encontrados
    data_conflicto = np.vstack(conflictos_acumulados)
    print(f"    ¡TOTAL PUNTOS INFRACTORES: {len(data_conflicto)}!")
    
    del conflictos_acumulados
    gc.collect()

    # ---------------------------------------------------------
    # FASE 3: CLUSTERING Y REPORTE
    # ---------------------------------------------------------
    print("--> [FASE 3/3] Agrupando alertas (DBSCAN)...")
    
    # Ahora sí, DBSCAN sobre los puntos filtrados (que deberían caber en RAM de sobra)
    # data_conflicto columnas: [0:x, 1:y, 2:z, 3:time]
    
    db = DBSCAN(eps=CONFIG["CLUSTER_EPS"], min_samples=CONFIG["CLUSTER_MIN_SAMPLES"]).fit(data_conflicto[:, :3])
    labels = db.labels_
    
    # Preparar DataFrame para facilitar el output
    df = pd.DataFrame(data_conflicto, columns=['x', 'y', 'z', 'gps_time'])
    df['cluster_id'] = labels
    
    # Filtrar ruido (-1)
    df = df[df['cluster_id'] != -1]
    
    lista_alertas = []
    
    for cid, grupo in df.groupby('cluster_id'):
        bbox = {
            "min_x": float(grupo.x.min()), "max_x": float(grupo.x.max()),
            "min_y": float(grupo.y.min()), "max_y": float(grupo.y.max()),
            "min_z": float(grupo.z.min()), "max_z": float(grupo.z.max())
        }
        centroide = {
            "x": float((bbox["min_x"] + bbox["max_x"]) / 2),
            "y": float((bbox["min_y"] + bbox["max_y"]) / 2),
            "z": float((bbox["min_z"] + bbox["max_z"]) / 2)
        }
        
        alerta = {
            "id_alerta": int(cid),
            "n_puntos": int(len(grupo)),
            "centroide": centroide,
            "gps_time_avg": float(grupo.gps_time.mean()),
            "bbox_3d": bbox
        }
        lista_alertas.append(alerta)

    with open(output_path, 'w') as f:
        json.dump(lista_alertas, f, indent=4)
        
    print(f"--> ¡LISTO! {len(lista_alertas)} alertas guardadas en: {output_path}")

if __name__ == "__main__":
    # Asegúrate que el archivo input existe
    generar_alertas_streaming(CONFIG["INPUT_FILE"], CONFIG["OUTPUT_JSON"])