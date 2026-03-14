import os, asyncio, json, requests, random
import google.genai as genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import edge_tts

# Temáticas de alta retención para viralizar
TEMAS = ["psicología oscura", "datos que podrían salvarte la vida", "curiosidades aterradoras", "misterios sin resolver"]

async def fabricar_video():
    try:
        # 1. Generar Guion Viral
        client = genai.Client(api_key=os.getenv('GEMINI_API'))
        tema = random.choice(TEMAS)
        prompt = f"Escribe un guion para un YouTube Short de {tema}. Que sea intrigante y directo. Máximo 35 palabras. Solo el texto."
        res = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        script = res.text.strip()
        print(f"🎙️ Guion: {script}")

        # 2. Voz de Tomas (Neural Argentina)
        await edge_tts.Communicate(script, "es-AR-TomasNeural").save("audio.mp3")

        # 3. Video de Fondo (Pexels)
        h = {"Authorization": os.getenv('PEXELS_API')}
        query = random.choice(["darkness", "mystery", "forest", "rain", "abstract"])
        v_res = requests.get(f"https://api.pexels.com/videos/search?query={query}&per_page=5", headers=h).json()
        video_url = random.choice(v_res['videos'])['video_files'][0]['link']
        with open("raw.mp4", "wb") as f: f.write(requests.get(video_url).content)

        # 4. FFmpeg: Formato Vertical 9:16 y corrección de píxeles (Números Pares)
        # Esta fórmula asegura que el video siempre sea divisible por 2 para que no falle.
        os.system("ffmpeg -y -i raw.mp4 -i audio.mp3 -vf 'scale=trunc(ih*(9/16)/2)*2:trunc(ih/2)*2,setsar=1' -c:v libx264 -c:a aac -shortest final.mp4")

        # 5. Subida Automática a YouTube
        info = json.loads(os.getenv('YT_TOKEN'))
        creds = Credentials.from_authorized_user_info(info)
        if creds.expired: creds.refresh(Request())
        
        yt = build("youtube", "v3", credentials=creds)
        yt.videos().insert(
            part="snippet,status",
            body={
                "snippet": {"title": "Dato del día #shorts #curiosidades", "categoryId": "22"},
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
            },
            media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
        ).execute()
        print("🚀 ¡VIDEO PUBLICADO!")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(fabricar_video())
