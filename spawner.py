import threading
import queue
import requests
import time
from datetime import datetime

URL_SERVIDOR = "http://127.0.0.1:5000/solicitar_boleto"
TOTAL_SOLICITUDES = 100
HILOS_CONCURRENTES = 100
VENTANA_TIEMPO_SEG = 60

cola_bitacora = queue.Queue()
barrera = threading.Barrier(HILOS_CONCURRENTES)
semaforo_concurrencia = threading.Semaphore(25)

resultados_metricas = []
lock_metricas = threading.Lock()


def tarea_spawner(hilo_id):
    barrera.wait()
    time.sleep((hilo_id % 10) * 0.05)

    hora_envio = datetime.now()
    payload = {"hilo_id": f"Spawner-{hilo_id}"}

    with semaforo_concurrencia:
        try:
            respuesta = requests.post(URL_SERVIDOR, json=payload, timeout=15)
            hora_respuesta = datetime.now()
            estado = "EXITO" if respuesta.status_code == 200 else "RECHAZADO"
        except Exception:
            hora_respuesta = datetime.now()
            estado = "ERROR"

    cola_bitacora.put({
        "hilo_id": f"Spawner-{hilo_id}",
        "hora_envio": hora_envio,
        "hora_respuesta": hora_respuesta,
        "estado": estado
    })


def hilo_consumidor_bitacora():
    while True:
        item = cola_bitacora.get()
        if item is None:
            cola_bitacora.task_done()
            break
        duracion = (item["hora_respuesta"] - item["hora_envio"]).total_seconds()
        with lock_metricas:
            resultados_metricas.append({
                "hilo": item["hilo_id"],
                "estado": item["estado"],
                "duracion": duracion
            })
        cola_bitacora.task_done()


consumidor = threading.Thread(target=hilo_consumidor_bitacora, daemon=True)
consumidor.start()

print(f"[*] Lanzando {TOTAL_SOLICITUDES} hilos concurrentes...")
inicio_global = time.time()

hilos = []
for i in range(TOTAL_SOLICITUDES):
    t = threading.Thread(target=tarea_spawner, args=(i + 1,))
    hilos.append(t)
    t.start()

for t in hilos:
    t.join()

fin_global = time.time()
tiempo_total = fin_global - inicio_global

cola_bitacora.put(None)
cola_bitacora.join()

print("\n=== REPORTE DE MÉTRICAS MONGODB ===")
print(f"Tiempo total transcurrido: {tiempo_total:.2f} segundos (Meta: <= {VENTANA_TIEMPO_SEG}s)")
exitos = sum(1 for r in resultados_metricas if r["estado"] == "EXITO")
rechazos = sum(1 for r in resultados_metricas if r["estado"] == "RECHAZADO")
errores = sum(1 for r in resultados_metricas if r["estado"] == "ERROR")

duraciones = [r["duracion"] for r in resultados_metricas if r["duracion"] > 0]
promedio_respuesta = sum(duraciones) / len(duraciones) if duraciones else 0

print(f"Boletos exitosos: {exitos}")
print(f"Rechazados (Aforo lleno): {rechazos}")
print(f"Errores de red/timeout: {errores}")
print(f"Tiempo promedio de respuesta: {promedio_respuesta:.4f} segundos")
print(f"Throughput (Rendimiento): {TOTAL_SOLICITUDES / tiempo_total:.2f} boletos/segundo")
