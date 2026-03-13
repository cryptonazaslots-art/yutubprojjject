import os, asyncio, json, edge_tts, requests
import google.generativeai as genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

async def fabricar_video():
    try:
        # 1. Guion con librería oficial
        genai.configure(api_key=os.getenv('GEMINI_API'))
        model = genai.GenerativeModel('gemini-1.5-flash')
        res = model.generate_content("Escribe un dato curioso del espacio de 30 palabras. Solo el texto.")
        script = res.text
        print(f"Guion: {script}")

        # 2. Voz
        await edge_tts.Communicate(script, "es-AR-TomasNeural").save("audio.mp3")

        # 3. Video (Pexels)
        h = {"Authorization": os.getenv('PEXELS_API')}
        v = requests.get("https://api.pexels.com/videos/search?query=galaxy&per_page=1", headers=h).json()
        with open("video.mp4", "wb") as f: f.write(requests.get(v['videos'][0]['video_files'][0]['link']).content)
        
        # 4. FFmpeg
        os.system("ffmpeg -y -i video.mp4 -i audio.mp3 -vf 'crop=ih*(9/16):ih' -c:a aac -shortest final.mp4")

        # 5. YouTube
        creds = Credentials.from_authorized_user_info(json.loads(os.getenv('YT_TOKEN')))
        if creds.expired: creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds)
        yt.videos().insert(
            part="snippet,status",
            body={"snippet": {"title": "Dato Espacial #shorts", "categoryId": "22"}, "status": {"privacyStatus": "public"}},
            media_body=MediaFileUpload("final.mp4")
        ).execute()
        print("LOGRADO.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__": asyncio.run(fabricar_video())
