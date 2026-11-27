from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client["auditorio_plata"]

db.evento.drop()
db.boleto.drop()
db.bitacora_solicitudes.drop()

db.evento.insert_one({
    "id_evento": 1,
    "nombre": "Concierto Navideño",
    "aforo_maximo": 20000,
    "aforo_actual": 0
})

db.boleto.create_index("folio", unique=True)
db.bitacora_solicitudes.create_index("hilo_id")

print("[OK] Base de datos 'auditorio_plata' inicializada con aforo máximo de 20,000.")
#print("[OK] Modo PRUEBA SIN SINCRONIZACION: aforo_maximo = 5")
