import os
import logging
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- Servidor HTTP para Render ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# --- CONFIGURACIÓN DE CLAVES Y CLIENTE ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicialización del cliente con la nueva SDK de Google
client = genai.Client(api_key=GEMINI_API_KEY)

PROMPT_SISTEMA = """
Eres un asistente de nutrición experto para un usuario en Colombia de 58 kg.
Analiza los alimentos que el usuario te mencione en lenguaje natural, calcula o estima sus gramos de proteína y calorías (kcal), y confirma el registro.

Instrucciones:
1. Responde brevemente confirmando lo que vas a registrar.
2. AL FINAL de tu respuesta, agrega STRICTAMENTE una nueva línea con el formato JSON de esta forma:
DATA_JSON: {"alimentos": [{"nombre": "Huevo", "proteina": 12, "kcal": 140}]}
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "registro_diario" not in context.user_data:
        context.user_data["registro_diario"] = []

    await update.message.reply_text(
        "¡Hola! Soy tu asistente de nutrición con IA 🤖💪\n\n"
        "Escríbeme lo que vas comiendo como prefieras. Ejemplo:\n"
        "• 'Almorcé 1.5 tazas de arroz con 1 lata de atún y 4 cucharadas de lentejas'\n"
        "• 'Me comí 3 huevos cocidos'\n\n"
        "Comandos:\n"
        "/resumen - Ver el desglose y total acumulado del día\n"
        "/reiniciar - Empezar un nuevo día"
    )

async def procesar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "registro_diario" not in context.user_data:
        context.user_data["registro_diario"] = []

    texto_usuario = update.message.text
    prompt_completo = f"{PROMPT_SISTEMA}\n\nEl usuario dice: '{texto_usuario}'"

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt_completo
        )
        respuesta_texto = response.text

        if "DATA_JSON:" in respuesta_texto:
            partes = respuesta_texto.split("DATA_JSON:")
            mensaje_para_usuario = partes[0].strip()
            json_str = partes[1].strip()

            try:
                datos = json.loads(json_str)
                for item in datos.get("alimentos", []):
                    context.user_data["registro_diario"].append(item)
            except Exception as e:
                logging.error(f"Error parseando JSON: {e}")
            
            await update.message.reply_text(mensaje_para_usuario)
        else:
            await update.message.reply_text(respuesta_texto)

    except Exception as e:
        await update.message.reply_text(f"❌ Ocurrió un error con la IA: {e}")

async def ver_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    registro = context.user_data.get("registro_diario", [])
    
    if not registro:
        await update.message.reply_text("Aún no has registrado ningún alimento hoy.")
        return

    total_prot = sum(item.get("proteina", 0) for item in registro)
    total_kcal = sum(item.get("kcal", 0) for item in registro)

    lineas = [f"• {item.get('nombre', 'Alimento')}: {item.get('proteina', 0)}g prot | {item.get('kcal', 0)} kcal" for item in registro]
    desglose = "\n".join(lineas)

    mensaje = (
        f"📋 *RESUMEN DE ALIMENTOS HOY*\n"
        f"-----------------------------------\n"
        f"{desglose}\n\n"
        f"🥩 *Proteína Total:* {total_prot}g\n"
        f"🔥 *Calorías Totales:* {total_kcal} kcal\n"
        f"🎯 *Meta diaria sugerida:* ~100g proteína"
    )
    await update.message.reply_text(mensaje, parse_mode="Markdown")

async def reiniciar_dia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["registro_diario"] = []
    await update.message.reply_text("🔄 Registro del día reiniciado. ¡Listo para un nuevo día!")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", ver_resumen))
    app.add_handler(CommandHandler("reiniciar", reiniciar_dia))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje))

    print("Bot con IA en marcha...")
    app.run_polling()
