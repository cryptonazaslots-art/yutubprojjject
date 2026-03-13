import os, requests, edge_tts, asyncio, json
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

async def fabricar_video():
    # 1. Guion (Gemini)
    url_g = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={os.getenv('GEMINI_API')}"
    p = {"contents": [{"parts":[{"text": "Escribe un dato curioso del espacio de 40 palabras. Solo el texto."}]}]}
    script = requests.post(url_g, json=p).json()['candidates'][0]['content']['parts'][0]['text']
    
    # 2. Voz (Edge-TTS)
    await edge_tts.Communicate(script, "es-AR-TomasNeural").save("audio.mp3")
    
    # 3. Video (Pexels)
    h = {"Authorization": os.getenv('PEXELS_API')}
    v = requests.get("https://api.pexels.com/videos/search?query=galaxy&per_page=1", headers=h).json()
    v_url = v['videos'][0]['video_files'][0]['link']
    with open("video.mp4", "wb") as f: f.write(requests.get(v_url).content)

    # 4. Montaje (FFmpeg)
    os.system("ffmpeg -i video.mp4 -i audio.mp3 -c:v copy -c:a aac -shortest final.mp4")
    
    # 5. Subir a YouTube
    info = json.loads(os.getenv('YT_TOKEN'))
    creds = Credentials.from_authorized_user_info(info)
    if creds.expired: creds.refresh(Request())
    
    yt = build("youtube", "v3", credentials=creds)
    yt.videos().insert(part="snippet,status", body={"snippet": {"title": "Dato Espacial #shorts", "categoryId": "22"}, "status": {"privacyStatus": "public"}},
        media_body="final.mp4").execute()
    print("Video subido.")

if __name__ == "__main__": asyncio.run(fabricar_video())
