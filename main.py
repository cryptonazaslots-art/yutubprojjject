import os, asyncio, json, requests, random
import google.genai as genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import edge_tts

# --- CONFIGURACIÓN ---
DATA_CURIO_EMERGENCIA = "El Sol es tan grande que dentro de él cabrían 1.3 millones de Tierras."

async def obtener_guion():
    try:
        client = genai.Client(api_key=os.getenv('GEMINI_API'))
        prompt = "Escribe un dato curioso del espacio. Máximo 30 palabras. Solo el texto, sin títulos."
        res = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return res.text.strip()
    except Exception as e:
        print(f"⚠️ Error Gemini: {e}. Usando dato de emergencia.")
        return DATA_CURIO_EMERGENCIA

async def fabricar_video():
    try:
        # 1. Guion y Voz
        script = await obtener_guion()
        print(f"🎙️ Guion: {script}")
        await edge_tts.Communicate(script, "es-AR-TomasNeural").save("audio.mp3")

        # 2. Footage (Pexels)
        h = {"Authorization": os.getenv('PEXELS_API')}
        query = random.choice(["galaxy", "nebula", "mars", "earth from space", "stars"])
        v_res = requests.get(f"https://api.pexels.com/videos/search?query={query}&per_page=1", headers=h).json()
        video_url = v_res['videos'][0]['video_files'][0]['link']
        
        with open("raw_video.mp4", "wb") as f:
            f.write(requests.get(video_url).content)

        # 3. Procesamiento Profesional (FFmpeg)
        # Este comando hace 3 cosas: Recorta a 9:16, centra la imagen y ajusta el audio.
        cmd = (
            "ffmpeg -y -i raw_video.mp4 -i audio.mp3 "
            "-vf 'scale=ih*(9/16):ih,boxblur=luma_radius=min(h\,w)/20:luma_power=1:chroma_radius=min(h\,w)/20:chroma_power=1,setsar=1' "
            "-c:v libx264 -aspect 9:16 -c:a aac -shortest final.mp4"
        )
        os.system(cmd)

        # 4. Subida a YouTube
        creds = Credentials.from_authorized_user_info(json.loads(os.getenv('YT_TOKEN')))
        if creds.expired: creds.refresh(Request())
        
        youtube = build("youtube", "v3", credentials=creds)
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": "Dato Espacial del Día #shorts",
                    "description": "Ciencia y curiosidades diarias. #espacio #astronomia",
                    "categoryId": "27" # Educación
                },
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
            },
            media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
        )
        request.execute()
        print("✅ ¡ÉXITO TOTAL! Video en YouTube.")

    except Exception as e:
        print(f"❌ FALLO CRÍTICO: {e}")

if __name__ == "__main__":
    asyncio.run(fabricar_video())
