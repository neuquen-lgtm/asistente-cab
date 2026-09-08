import asyncio
import websockets
import json
import requests
import urllib3
import base64
import time
import os 

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. TUS LLAVES (¡Ahora protegidas y ocultas para la nube!)
API_KEY = os.environ.get("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = "6Mo5ciGH5nWiQacn5FYk" # El ID de la voz no es secreto, puede quedar

# 2. FUNCIONES DE IA Y VOZ
def obtener_respuesta_gemini(texto_usuario):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={API_KEY}"
    
    procedimientos_texto = ""
    try:
        with open("procedimientos.json", "r", encoding="utf-8") as archivo:
            datos_json = json.load(archivo)
            palabras_clave = [p.lower() for p in texto_usuario.split() if len(p) > 3]
            manuales_relevantes = []
            for manual in datos_json:
                texto_manual = (manual.get("tema", "") + " " + manual.get("contenido", "")).lower()
                puntos = sum(1 for palabra in palabras_clave if palabra in texto_manual)
                if puntos > 0:
                    manuales_relevantes.append((puntos, manual))
            
            manuales_relevantes.sort(key=lambda x: x[0], reverse=True)
            mejores_manuales = [m[1] for m in manuales_relevantes[:1]]
            
            if mejores_manuales:
                procedimientos_texto = json.dumps(mejores_manuales, ensure_ascii=False)
            else:
                procedimientos_texto = "No hay manuales sobre esto."
                
    except Exception as e:
        procedimientos_texto = "Base de datos no disponible."

    mensaje_completo = (
        "Actúa como 'CAB', la Asistente Técnica Central de 'Control CAB'.\n"
        "Basate estrictamente en este manual de la empresa para responder:\n"
        f"{procedimientos_texto}\n\n"
        "TUS REGLAS OBLIGATORIAS:\n"
        "1. NO USES ASTERISCOS (*), ni guiones bajos, ni negritas. Escribe en texto plano.\n"
        "2. Usa etiquetas HTML <br> para separar los pasos y que se lean bien en pantalla.\n"
        "3. Habla de forma muy LENTA y PAUSADA separando ideas con puntos y comas.\n"
        f"El técnico te pregunta: {texto_usuario}"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": mensaje_completo}]}]
    }

    for intento in range(5):
        try:
            respuesta = requests.post(url, json=payload, verify=False)
            datos = respuesta.json()
            if 'error' in datos:
                mensaje_error = datos['error'].get('message', 'Error desconocido')
                if "high demand" in mensaje_error.lower() or "overloaded" in mensaje_error.lower() or "503" in str(mensaje_error) or "429" in str(mensaje_error):
                    time.sleep(4)
                    continue
                else:
                    return "Error de permisos en la base de datos."
            return datos['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            time.sleep(4)
            
    return "Servidores saturados. Intenta en un minuto."

def obtener_audio_elevenlabs(texto):
    texto_limpio = texto.replace("<br>", ". ") 
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": texto_limpio,
        "model_id": "eleven_multilingual_v2", 
        "voice_settings": {"stability": 0.40, "similarity_boost": 0.75}
    }
    try:
        respuesta = requests.post(url, json=data, headers=headers)
        if respuesta.status_code == 200:
            return base64.b64encode(respuesta.content).decode('utf-8')
        return None
    except:
        return None

# 3. LÓGICA WEBSOCKET
async def logica_asistente(websocket):
    print("POS Conectado. CAB lista.")
    try:
        async for mensaje in websocket:
            datos = json.loads(mensaje)

            if datos.get("accion") == "procesar_texto":
                texto_recibido = datos.get("texto", "")
                
                print(f"\nTécnico: {texto_recibido}")
                print("Estado: Buscando respuesta...")
                
                await websocket.send(json.dumps({"estado": "estado-procesando"}))

                respuesta_ia = obtener_respuesta_gemini(texto_recibido)
                print(f"CAB: {respuesta_ia}")
                print("Estado: Generando voz...")
                
                audio_b64 = obtener_audio_elevenlabs(respuesta_ia)

                if audio_b64:
                    await websocket.send(json.dumps({
                        "estado": "estado-respondiendo",
                        "audio": audio_b64,
                        "texto_pantalla": respuesta_ia 
                    }))
                    await asyncio.sleep(len(respuesta_ia) * 0.08)
                else:
                    await websocket.send(json.dumps({
                        "estado": "estado-respondiendo",
                        "texto": respuesta_ia,
                        "texto_pantalla": respuesta_ia 
                    }))
                    await asyncio.sleep(len(respuesta_ia) * 0.08)

                await websocket.send(json.dumps({"estado": "estado-reposo"}))
                print("Estado: Reposo.")

    except websockets.exceptions.ConnectionClosed:
        print("El POS se ha desconectado.")

async def main():
    puerto = int(os.environ.get("PORT", 8765))
    async with websockets.serve(logica_asistente, "0.0.0.0", puerto):
        print(f"Cerebro Técnico activado en el puerto {puerto}. ¡Lista para la nube!")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())