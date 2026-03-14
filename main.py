import os, asyncio, json, requests, random, subprocess
import google.genai as genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import edge_tts

# Nicho de alta retención: Curiosidades y Psicología
TEMAS = ["psicología oscura", "datos que podrían salvarte la vida", "curiosidades aterradoras"]

async def fabricar_video():
    try:
        # 1. Gemini 2026 (Usando la nueva SDK estable)
        client = genai.Client(api_key=os.getenv('GEMINI_API'))
        tema = random.choice(TEMAS)
        prompt = f"Escribe un guion para un Short de YouTube sobre {tema}. Sé intrigante. Máximo 30 palabras. Solo el texto."
        
        # Forzamos la versión estable del modelo para evitar el error 404
        res = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        script = res.text.strip()
        print(f"🎙️ Guion generado: {script}")

        # 2. Generar Audio
        await edge_tts.Communicate(script, "es-AR-TomasNeural").save("audio.mp3")

        # 3. Video de Fondo (Pexels)
        h = {"Authorization": os.getenv('PEXELS_API')}
        query = random.choice(["mysterious", "dark nature", "ocean", "texture"])
        v_res = requests.get(f"https://api.pexels.com/videos/search?query={query}&per_page=3", headers=h).json()
        video_url = v_res['videos'][0]['video_files'][0]['link']
        with open("raw.mp4", "wb") as f: f.write(requests.get(video_url).content)

        # 4. FFmpeg con corrección de escala (FUERZA NÚMEROS PARES)
        # Aquí es donde arreglamos el error de 'width not divisible by 2' que viste en la captura.
        cmd = [
            'ffmpeg', '-y', '-i', 'raw.mp4', '-i', 'audio.mp3',
            '-vf', 'scale=trunc(ih*(9/16)/2)*2:trunc(ih/2)*2,setsar=1',
            '-c:v', 'libx264', '-c:a', 'aac', '-shortest', 'final.mp4'
        ]
        subprocess.run(cmd, check=True)

        # 5. VERIFICACIÓN: ¿Existe el video?
        if not os.path.exists("final.mp4"):
            raise Exception("FFmpeg falló al generar el archivo final.")

        # 6. Subida a YouTube
        info = json.loads(os.getenv('YT_TOKEN'))
        creds = Credentials.from_authorized_user_info(info)
        if creds.expired: creds.refresh(Request())
        
        yt = build("youtube", "v3", credentials=creds)
        yt.videos().insert(
            part="snippet,status",
            body={"snippet": {"title": "Dato del día #shorts", "categoryId": "22"}, "status": {"privacyStatus": "public"}},
            media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
        ).execute()
        
        print("✅ ¡LOGRADO! El video ya está en tu canal.")

    except Exception as e:
        print(f"❌ FALLO REAL: {e}")

if __name__ == "__main__":
    asyncio.run(fabricar_video())
