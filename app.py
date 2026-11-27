from flask import Flask, request, jsonify, send_file, render_template
from pymongo import MongoClient
import qrcode
import io
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import threading
import time
from datetime import datetime

app = Flask(__name__)

MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client["auditorio_plata"]

lock_servidor = threading.Lock()


def generar_pdf_boleto(folio, fecha_hora):
    buffer = io.BytesIO()
    qr_data = f"AUDITORIO PLATA - Folio: {folio:05d} - Fecha: {fecha_hora}"
    qr = qrcode.QRCode(box_size=5, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="#0f172a", back_color="white")

    os.makedirs("/tmp", exist_ok=True)
    qr_path = f"/tmp/temp_qr_{folio}.png"
    img_qr.save(qr_path)

    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.setStrokeColorRGB(0.06, 0.09, 0.16)
    c.setLineWidth(3)
    c.rect(40, height - 360, width - 80, 320, stroke=1, fill=0)

    c.setFillColorRGB(0.06, 0.09, 0.16)
    c.rect(40, height - 90, width - 80, 50, stroke=0, fill=1)

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(60, height - 62, "AUDITORIO PLATA")

    c.setFont("Helvetica", 12)
    c.drawRightString(width - 60, height - 62, "PASE DE ACCESO VIP")

    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, height - 125, "Concierto Navideño")

    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(60, height - 145, "Recinto Oficial: Auditorio Plata")
    c.drawString(60, height - 165, f"Fecha y Hora de Emisión: {fecha_hora}")

    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.setFillColorRGB(0.95, 0.97, 1)
    c.roundRect(60, height - 260, 240, 70, 8, stroke=1, fill=1)

    c.setFillColorRGB(0.06, 0.09, 0.16)
    c.setFont("Helvetica", 9)
    c.drawString(75, height - 215, "FOLIO OFICIAL DE ENTRADA")
    c.setFont("Helvetica-Bold", 22)
    c.drawString(75, height - 245, f"#{folio:05d}")

    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.rect(width - 210, height - 335, 150, 150, stroke=1, fill=0)
    c.drawImage(qr_path, width - 205, height - 330, width=140, height=140)

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(60, height - 335, "Documento personal e intransferible.")
    c.drawString(60, height - 347, "Presente este código QR en el acceso del auditorio.")

    c.save()
    buffer.seek(0)

    if os.path.exists(qr_path):
        os.remove(qr_path)
    return buffer


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/estado', methods=['GET'])
def api_estado():
    evento = db.evento.find_one({"id_evento": 1})
    if not evento:
        return jsonify({"aforo_maximo": 20000, "aforo_actual": 0})
    return jsonify({
        "aforo_maximo": evento.get("aforo_maximo", 20000),
        "aforo_actual": evento.get("aforo_actual", 0)
    })


@app.route('/api/validar/<int:folio>', methods=['GET'])
def api_validar(folio):
    boleto = db.boleto.find_one({"folio": folio})
    if boleto:
        return jsonify({
            "valido": True,
            "folio": boleto["folio"],
            "hilo_id": boleto["hilo_id"],
            "fecha": str(boleto["fecha_emision"])
        })
    return jsonify({"valido": False})

@app.route('/solicitar_boleto', methods=['POST'])
def solicitar_boleto():
    datos = request.json or {}
    hilo_id = datos.get("hilo_id", "Desconocido")
    hora_envio = datetime.now()

    try:
        with lock_servidor:
            evento = db.evento.find_one_and_update(
                {"id_evento": 1, "$expr": {"$lt": ["$aforo_actual", "$aforo_maximo"]}},
                {"$inc": {"aforo_actual": 1}},
                return_document=True
            )

            if not evento:
                db.bitacora_solicitudes.insert_one({
                    "hilo_id": hilo_id,
                    "hora_envio": hora_envio,
                    "hora_respuesta": datetime.now(),
                    "folio": None,
                    "estado": "RECHAZADO"
                })
                return jsonify({"estado": "RECHAZADO", "mensaje": "Aforo lleno"}), 400

            folio = evento["aforo_actual"]
            ahora = datetime.now()
            fecha_hora_str = ahora.strftime("%Y-%m-%d %H:%M:%S")

            db.boleto.insert_one({
                "folio": folio,
                "id_evento": 1,
                "hilo_id": hilo_id,
                "fecha_emision": ahora
            })

            db.bitacora_solicitudes.insert_one({
                "hilo_id": hilo_id,
                "hora_envio": hora_envio,
                "hora_respuesta": datetime.now(),
                "folio": folio,
                "estado": "EXITO"
            })

        pdf_buffer = generar_pdf_boleto(folio, fecha_hora_str)
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"boleto_{folio}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        db.bitacora_solicitudes.insert_one({
            "hilo_id": hilo_id,
            "hora_envio": hora_envio,
            "hora_respuesta": datetime.now(),
            "folio": None,
            "estado": "ERROR"
        })
        return jsonify({"estado": "ERROR", "detalle": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
