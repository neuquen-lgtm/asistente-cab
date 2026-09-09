import asyncio
import websockets
import json
import requests
import base64
import os
import google.generativeai as genai

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
VOICE_ID = "6Mo5ciGH5nWiQacn5FYk" 

if API_KEY:
    genai.configure(api_key=API_KEY)

def obtener_respuesta_gemini(texto_usuario):
    if not API_KEY:
        return "Error: Falta la llave de Google en Render."
    
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
                procedimientos_texto = "No hay manuales específicos, pero intentaré ayudar."
                
    except Exception as e:
        procedimientos_texto = "Base de datos no disponible."

    mensaje_completo = (
        "Eres 'CAB', Asistente Técnica de 'Control CAB'.\n"
        "Usa este manual para responder:\n"
        f"{procedimientos_texto}\n\n"
        "TUS REGLAS OBLIGATORIAS:\n"
        "1. SÉ EXTREMADAMENTE DIRECTA Y BREVE. No des introducciones ni expliques desde el principio.\n"
        "2. Ve directo al paso o a la solución que necesita el técnico.\n"
        "3. NO uses asteriscos (*), ni negritas, ni etiquetas HTML.\n"
        "4. Habla con oraciones cortas y separadas por puntos.\n"
        f"El técnico pregunta: {texto_usuario}"
    )

    # CÓDIGO INDESTRUCTIBLE: Prueba varios modelos en cascada por si Google falla
    modelos_a_probar = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-1.0-pro', 'gemini-pro']
    ultimo_error = ""
    
    for nombre_modelo in modelos_a_probar:
        try:
            modelo = genai.GenerativeModel(nombre_modelo)
            respuesta = modelo.generate_content(mensaje_completo)
            return respuesta.text
        except Exception as e:
            ultimo_error = str(e)
            continue # Si este modelo falla, salta automáticamente al siguiente
            
    return f"Google rechazó todos los modelos. Último error: {ultimo_error}"

def obtener_audio_elevenlabs(texto):
    if not ELEVENLABS_API_KEY:
        return None
        
    texto_limpio = texto.replace("*", "").replace("_", "") 
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

async def logica_asistente(websocket):
    try:
        async for mensaje in websocket:
            datos = json.loads(mensaje)

            if datos.get("accion") == "procesar_texto":
                texto_recibido = datos.get("texto", "")
                await websocket.send(json.dumps({"estado": "estado-procesando"}))

                respuesta_ia = obtener_respuesta_gemini(texto_recibido)
                audio_b64 = obtener_audio_elevenlabs(respuesta_ia)

                await websocket.send(json.dumps({
                    "estado": "estado-respondiendo",
                    "audio": audio_b64,
                    "texto_pantalla": respuesta_ia 
                }))

                await websocket.send(json.dumps({"estado": "estado-reposo"}))

    except websockets.exceptions.ConnectionClosed:
        pass

async def main():
    puerto = int(os.environ.get("PORT", 8765))
    async with websockets.serve(logica_asistente, "0.0.0.0", puerto):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
