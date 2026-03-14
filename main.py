"""
ViralEngine V8
Fixes vs V7:
- Audio: loudnorm a -14dB (estándar YouTube) + compresión de silencios a 0.4s máx
- Subtítulos: fuente DejaVu Sans Bold (instalada en Ubuntu por defecto, no Arial Black)
- Video: upscale lanczos + bitrate fijo 4Mbps → calidad percibida alta aunque source sea 720p
- Transiciones: crossfade de 0.5s entre clips (no corte seco)
"""

import os, sys, asyncio, json, re, requests, random, subprocess
from google import genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import edge_tts

MODELO    = "gemini-2.5-flash-lite"
VOZ       = "es-ES-AlvaroNeural"
VELOCIDAD = "+0%"   # sin slowdown — los silencios se comprimen en post, no en la voz
PITCH     = "-4Hz"

MUSICA_URLS = [
    "https://cdn.pixabay.com/download/audio/2022/03/10/audio_2dde668d05.mp3",
    "https://cdn.pixabay.com/download/audio/2023/01/10/audio_8ea684a6d0.mp3",
    "https://cdn.pixabay.com/download/audio/2022/10/25/audio_946f8c0e5a.mp3",
]

NICHOS_DEFAULT = [
    "Marco Aurelio y el control de las emociones",
    "Séneca sobre el uso del tiempo",
    "Epicteto y la dicotomía del control",
    "el efecto ancla en decisiones cotidianas",
    "sesgo de confirmación: por qué creemos lo que creemos",
    "la historia perturbadora del experimento de Milgram",
    "el estoicismo aplicado al trabajo moderno",
    "por qué el cerebro humano sabotea tus propias metas",
    "el estoicismo y el miedo al fracaso",
    "por qué Marco Aurelio escribía para nadie",
]

QUERIES_VIDEO = [
    "ancient rome cinematic",
    "philosophy nature contemplation",
    "dark moody atmospheric",
    "stoic warrior silhouette",
    "ancient greece ruins",
    "ocean meditation calm",
    "mountains epic landscape",
    "dark forest cinematic",
    "roman soldier epic",
    "renaissance painting dramatic",
]

PALABRAS_CLAVE = {
    "nunca","jamás","secreto","nadie","todo","nada","siempre","verdad",
    "mentira","miedo","poder","libre","muerte","vida","mente","control",
    "trampa","error","clave","único","real","falso","hoy","ya","basta",
    "atención","peligro","importante","crítico","descubrí","probado",
    "científico","demostrado","sorprendente","increíble","manipulación",
    "oculto","prohibido","silencio","oscuro","brutal","imposible","gratis",
}

DESCRIPCION_TEMPLATE = """{hook}

🏛️ Canal de filosofía estoica y psicología aplicada.
📌 Un dato que cambia tu perspectiva — cada día.
✅ Suscribite para no perderte ninguno.

━━━━━━━━━━━━━━━━━━━━━━
🔎 SOBRE ESTE VIDEO
━━━━━━━━━━━━━━━━━━━━━━
{descripcion_extendida}

━━━━━━━━━━━━━━━━━━━━━━
📚 TAGS
━━━━━━━━━━━━━━━━━━━━━━
#shorts #estoicismo #filosofia #psicologia #mentalidad #viral
#marcaurelio #seneca #epicteto #sabiduria #motivacion #reflexion
#crecimientopersonal #inteligenciaemocional #datos #curiosidades
"""

TAGS = [
    "shorts","estoicismo","filosofia estoica","psicologia","mentalidad",
    "marco aurelio","seneca","epicteto","sabiduria","motivacion","reflexion",
    "crecimiento personal","inteligencia emocional","datos curiosos",
    "curiosidades","filosofia","viral","argentina","mente","autoconocimiento",
]

# ─────────────────────────────────────────────────────────────────────────────
# 1. Contenido + SEO
# ─────────────────────────────────────────────────────────────────────────────

def generar_contenido(tema: str, intento: int = 0) -> dict:
    if intento > 2:
        return {
            "guion": f"Esto que te voy a contar sobre {tema} va a cambiar cómo ves el mundo. " * 4,
            "gancho_pantalla": "¿Lo sabías?",
            "titulo": f"🏛️ {tema[:40]}",
            "hook_descripcion": "Una idea que cambia tu perspectiva.",
            "descripcion_extendida": f"Reflexión profunda sobre {tema}.",
            "filosofo": None,
        }

    client = genai.Client(api_key=os.environ["GEMINI_API"])
    prompt = f"""Sos un experto en SEO de YouTube y creador de contenido filosófico viral en español.

TEMA: {tema}

Generá TODO el contenido para un YouTube Short de 40-50 segundos.
El guion DEBE tener entre 95 y 115 palabras — CRÍTICO para la duración correcta.

Respondé ÚNICAMENTE con JSON válido, sin markdown, sin backticks.

{{
  "guion": "guion de 95-115 palabras. GANCHO (15 palabras): frase impactante que genere curiosidad o shock. DESARROLLO (65 palabras): explicación con filósofo o científico nombrado, ejemplo concreto de la vida cotidiana. CIERRE (15 palabras): reflexión poderosa que invite a suscribirse. Voseo argentino. Sin separadores ni símbolos.",
  "gancho_pantalla": "frase de máximo 5 palabras para mostrar en pantalla los primeros 2 segundos. Shock o curiosidad extrema.",
  "titulo": "título YouTube SEO máximo 60 caracteres con 1 emoji al inicio, sin hashtags",
  "hook_descripcion": "primera oración descripción generando curiosidad máximo 120 caracteres",
  "descripcion_extendida": "2-3 oraciones SEO sobre el tema máximo 250 caracteres",
  "filosofo": "nombre del filósofo si aplica o null"
}}"""

    response = client.models.generate_content(model=MODELO, contents=prompt)
    texto = re.sub(r"```json\s*|```\s*", "", response.text.strip()).strip()

    try:
        data = json.loads(texto)
        n = len(data.get("guion", "").split())
        print(f"📊 Guion: {n} palabras")
        if n < 75:
            print(f"⚠️  Muy corto ({n} palabras), reintentando...")
            return generar_contenido(tema, intento + 1)
        return data
    except json.JSONDecodeError:
        print(f"⚠️  JSON inválido (intento {intento+1})")
        return generar_contenido(tema, intento + 1)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Audio con silencios comprimidos
# ─────────────────────────────────────────────────────────────────────────────

async def generar_audio_y_tiempos(texto: str) -> tuple[float, list[dict]]:
    """
    Pasada 1: captura WordBoundary con tiempos exactos
    Pasada 2: guarda audio crudo
    Pasada 3: postprocesa con FFmpeg:
              - silenceremove: comprime silencios a máx 0.4s
              - loudnorm: normaliza a -14dB LUFS (estándar YouTube)
    """
    # Pasada 1 — tiempos
    palabras = []
    com1 = edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD, pitch=PITCH)
    async for chunk in com1.stream():
        if chunk["type"] == "WordBoundary":
            palabras.append({
                "word":  chunk["text"],
                "start": chunk["offset"] / 1e7,
                "end":   (chunk["offset"] + chunk["duration"]) / 1e7,
            })

    # Pasada 2 — audio crudo
    com2 = edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD, pitch=PITCH)
    await com2.save("audio_raw.mp3")

    # Pasada 3 — postproceso: comprimir silencios + loudnorm
    # silenceremove elimina silencios > 0.4s
    # loudnorm normaliza a -14 LUFS (estándar YouTube/Spotify)
    cmd = [
        "ffmpeg", "-y", "-i", "audio_raw.mp3",
        "-af", (
            "silenceremove=stop_periods=-1:stop_duration=0.4:stop_threshold=-40dB,"
            "loudnorm=I=-14:TP=-1.5:LRA=11"
        ),
        "audio.mp3"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("⚠️  Postproceso audio falló, usando raw")
        import shutil
        shutil.copy("audio_raw.mp3", "audio.mp3")

    # Duración del audio procesado
    r = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1","audio.mp3"],
        capture_output=True, text=True
    )
    duracion = float(r.stdout.strip()) if r.stdout.strip() else 40.0
    print(f"🔊 Audio procesado: {duracion:.1f}s — {len(palabras)} palabras")

    # Fallback timing si WordBoundary no funcionó
    if not palabras:
        print("⚠️  WordBoundary vacío, usando timing estimado")
        lista = texto.split()
        seg = duracion / max(len(lista), 1)
        t = 0.2
        for w in lista:
            palabras.append({"word": w, "start": t, "end": t + seg * 0.85})
            t += seg

    return duracion, palabras

# ─────────────────────────────────────────────────────────────────────────────
# 3. Subtítulos .ASS — fuente DejaVu (existe en Ubuntu por defecto)
# ─────────────────────────────────────────────────────────────────────────────

def generar_subtitulos_hormozi(palabras: list[dict], gancho: str, duracion_total: float) -> None:
    """
    Una palabra por vez — estilo Hormozi
    Fuente: DejaVu Sans Bold (garantizada en Ubuntu/GitHub Actions)
    Palabras clave: amarillo brillante (&H0000FFFF en ASS = BGRA)
    Resto: blanco con borde negro grueso
    """
    def fmt(s: float) -> str:
        h  = int(s // 3600)
        m  = int((s % 3600) // 60)
        sc = s % 60
        cs = int((sc % 1) * 100)
        return f"{h}:{m:02d}:{int(sc):02d}.{cs:02d}"

    # DejaVu Sans Bold — instalada por defecto en Ubuntu
    # Arial Black NO existe en GitHub Actions runner
    header = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Normal,DejaVu Sans Bold,78,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,1,0,1,4,1,2,60,60,220,1
Style: Key,DejaVu Sans Bold,78,&H0000FFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,1,0,1,4,1,2,60,60,220,1
Style: Gancho,DejaVu Sans Bold,70,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,1,0,1,5,1,5,60,60,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # El audio arranca 2 segundos después (gancho visual ocupa 0-2s)
    offset = 2.0

    with open("subs.ass", "w", encoding="utf-8") as f:
        f.write(header)

        # Gancho en pantalla: primeros 1.9 segundos
        if gancho:
            gancho_limpio = gancho.replace("{","").replace("}","")
            f.write(f"Dialogue: 0,{fmt(0.1)},{fmt(1.9)},Gancho,,0,0,0,,{gancho_limpio}\n")

        # Una palabra por vez
        for p in palabras:
            inicio = p["start"] + offset
            fin    = min(p["end"] + offset, duracion_total - 0.05)
            if inicio >= duracion_total:
                break

            word_lower = p["word"].lower().strip("¿?¡!.,;:\"'")
            estilo     = "Key" if word_lower in PALABRAS_CLAVE else "Normal"
            word_clean = p["word"].replace("{","").replace("}","").replace("\\","")
            f.write(f"Dialogue: 0,{fmt(inicio)},{fmt(fin)},{estilo},,0,0,0,,{word_clean}\n")

    print(f"📝 Subtítulos: {len(palabras)} palabras — fuente DejaVu Sans Bold")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Música
# ─────────────────────────────────────────────────────────────────────────────

def descargar_musica() -> bool:
    try:
        url = random.choice(MUSICA_URLS)
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open("music.mp3","wb") as f:
            f.write(r.content)
        print("🎵 Música descargada")
        return True
    except Exception as e:
        print(f"⚠️  Sin música: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# 5. Video — 3 clips + crossfade entre ellos
# ─────────────────────────────────────────────────────────────────────────────

def descargar_y_preparar_videos(duracion_necesaria: float) -> None:
    """
    - Descarga 3 clips con queries distintas
    - Normaliza cada uno a 1080x1920 con upscale lanczos
    - Aplica crossfade de 0.5s entre clips
    - Bitrate fijo 4Mbps para calidad consistente
    """
    headers = {"Authorization": os.environ["PEXELS_API"]}
    queries = random.sample(QUERIES_VIDEO, 3)
    clips_norm = []

    for i, query in enumerate(queries):
        url = (f"https://api.pexels.com/videos/search"
               f"?query={query}&per_page=10&orientation=portrait&size=large")
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            datos = r.json()
            videos = datos.get("videos", [])
            if not videos:
                continue

            largos = [v for v in videos if v.get("duration", 0) >= 8]
            video  = random.choice(largos if largos else videos)
            files  = video["video_files"]
            hd     = [f for f in files if f.get("height", 0) >= 1080]
            sd     = [f for f in files if f.get("quality") == "hd"]
            link   = (hd[0] if hd else (sd[0] if sd else files[0]))["link"]

            raw = f"clip_raw_{i}.mp4"
            with open(raw,"wb") as f:
                f.write(requests.get(link, timeout=60).content)

            # Normalizar: upscale lanczos a 1080x1920, sin audio, fps fijo 30
            norm = f"clip_norm_{i}.mp4"
            cmd = [
                "ffmpeg", "-y", "-i", raw,
                "-vf", (
                    "scale=1080:1920:force_original_aspect_ratio=decrease"
                    ":flags=lanczos,"
                    "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
                    "setsar=1,fps=30"
                ),
                "-c:v", "libx264", "-preset", "fast",
                "-b:v", "4M",       # bitrate fijo 4Mbps
                "-maxrate", "4M",
                "-bufsize", "8M",
                "-an",              # sin audio en clips de fondo
                norm,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                clips_norm.append(norm)
                # Duración del clip normalizado
                p = subprocess.run(
                    ["ffprobe","-v","error","-show_entries","format=duration",
                     "-of","default=noprint_wrappers=1:nokey=1", norm],
                    capture_output=True, text=True
                )
                dur = float(p.stdout.strip()) if p.stdout.strip() else 0
                print(f"🎬 Clip {i+1}: {query} — {dur:.1f}s normalizado a 1080p")

        except Exception as e:
            print(f"⚠️  Clip {i+1} falló ({query}): {e}")

    if not clips_norm:
        raise RuntimeError("No se descargó ningún clip de Pexels")

    if len(clips_norm) == 1:
        # Un solo clip: loop
        os.rename(clips_norm[0], "raw.mp4")
        print("ℹ️  Un clip — se aplicará loop")
        return

    # Concatenar con crossfade de 0.5s entre clips
    # xfade filter de FFmpeg: transition=fade, duration=0.5
    _construir_crossfade(clips_norm)


def _construir_crossfade(clips: list[str]) -> None:
    """
    Concatena N clips con crossfade de 0.5s entre cada par.
    Usa el filtro xfade de FFmpeg.
    """
    # Obtener duración de cada clip
    durs = []
    for c in clips:
        p = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1", c],
            capture_output=True, text=True
        )
        durs.append(float(p.stdout.strip()) if p.stdout.strip() else 15.0)

    if len(clips) == 2:
        offset = durs[0] - 0.5
        filtro = (
            f"[0:v][1:v]xfade=transition=fade:duration=0.5:offset={offset:.3f}[v]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", clips[0], "-i", clips[1],
            "-filter_complex", filtro,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "fast", "-b:v", "4M",
            "raw.mp4"
        ]
    else:
        # 3 clips: A→B→C con dos crossfades
        offset1 = durs[0] - 0.5
        offset2 = durs[0] + durs[1] - 1.0  # acumula los offsets
        filtro = (
            f"[0:v][1:v]xfade=transition=fade:duration=0.5:offset={offset1:.3f}[ab];"
            f"[ab][2:v]xfade=transition=fade:duration=0.5:offset={offset2:.3f}[v]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", clips[0], "-i", clips[1], "-i", clips[2],
            "-filter_complex", filtro,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "fast", "-b:v", "4M",
            "raw.mp4"
        ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("⚠️  Crossfade falló, usando concatenación simple")
        # Fallback: concat simple
        with open("concat.txt","w") as f:
            for c in clips:
                f.write(f"file '{os.path.abspath(c)}'\n")
        subprocess.run(
            ["ffmpeg","-y","-f","concat","-safe","0","-i","concat.txt",
             "-c","copy","raw.mp4"],
            capture_output=True
        )
    else:
        p = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1","raw.mp4"],
            capture_output=True, text=True
        )
        dur = float(p.stdout.strip()) if p.stdout.strip() else 0
        print(f"✅ Video con crossfade: {dur:.1f}s totales")

# ─────────────────────────────────────────────────────────────────────────────
# 6. FFmpeg final
# ─────────────────────────────────────────────────────────────────────────────

def procesar_video(duracion_audio: float, tiene_musica: bool) -> None:
    subs_abs      = os.path.abspath("subs.ass")
    duracion_total = duracion_audio + 2.5  # +2.5s gancho inicial

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,fps=30,ass={subs_abs}"
    )

    # Audio: voz con delay 2s + música al 12% + loudnorm final
    if tiene_musica:
        af = (
            "[1:a]adelay=2000|2000[voz];"
            "[2:a]volume=0.12[musica];"
            "[voz][musica]amix=inputs=2:duration=first,"
            "loudnorm=I=-14:TP=-1.5:LRA=11[audio_final]"
        )
        inputs = [
            "-stream_loop","-1","-i","raw.mp4",
            "-i","audio.mp3",
            "-stream_loop","-1","-i","music.mp3",
        ]
        maps = ["-map","0:v","-map","[audio_final]"]
    else:
        af = (
            "[1:a]adelay=2000|2000,"
            "loudnorm=I=-14:TP=-1.5:LRA=11[audio_final]"
        )
        inputs = [
            "-stream_loop","-1","-i","raw.mp4",
            "-i","audio.mp3",
        ]
        maps = ["-map","0:v","-map","[audio_final]"]

    cmd = (
        ["ffmpeg","-y"] + inputs +
        ["-filter_complex", af,
         "-vf", vf] +
        maps +
        ["-c:v","libx264","-preset","fast",
         "-b:v","4M","-maxrate","4M","-bufsize","8M",
         "-c:a","aac","-b:a","128k",
         "-t", str(duracion_total),
         "-movflags","+faststart",
         "final.mp4"]
    )

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg stderr:", result.stderr[-3000:])
        raise RuntimeError("FFmpeg final falló")

    p = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1","final.mp4"],
        capture_output=True, text=True
    )
    dur = float(p.stdout.strip()) if p.stdout.strip() else 0
    print(f"✂️  Video final: {dur:.1f}s — 1080p 4Mbps con subtítulos")

# ─────────────────────────────────────────────────────────────────────────────
# 7. YouTube
# ─────────────────────────────────────────────────────────────────────────────

def subir_a_youtube(datos: dict) -> None:
    info  = json.loads(os.environ["YT_TOKEN"])
    creds = Credentials.from_authorized_user_info(info)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    yt  = build("youtube","v3",credentials=creds)
    titulo = datos.get("titulo","🏛️ Sabiduría estoica del día")[:100]
    desc   = DESCRIPCION_TEMPLATE.format(
        hook=datos.get("hook_descripcion",""),
        descripcion_extendida=datos.get("descripcion_extendida",""),
    )
    body = {
        "snippet": {
            "title": titulo, "description": desc, "tags": TAGS,
            "categoryId": "27",
            "defaultLanguage": "es", "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False, "madeForKids": False,
        },
    }
    media = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    resp  = yt.videos().insert(
        part="snippet,status", body=body, media_body=media
    ).execute()
    vid = resp.get("id","")
    print(f"🚀 '{titulo}'")
    print(f"🔗 https://youtube.com/shorts/{vid}")

# ─────────────────────────────────────────────────────────────────────────────
# Flujo principal
# ─────────────────────────────────────────────────────────────────────────────

async def fabricar_video(tema: str):
    print(f"\n{'='*55}\n🎯 Tema: {tema}\n{'='*55}\n")

    datos   = generar_contenido(tema)
    guion   = datos.get("guion", tema).strip()
    gancho  = datos.get("gancho_pantalla", "¿Lo sabías?")
    titulo  = datos.get("titulo","🏛️ Sabiduría del día")
    print(f"📝 ({len(guion.split())} palabras): {guion[:80]}...")
    print(f"⚡ Gancho: {gancho} | 🏷️  {titulo}")

    duracion, palabras = await generar_audio_y_tiempos(guion)
    generar_subtitulos_hormozi(palabras, gancho, duracion + 2.5)
    tiene_musica = descargar_musica()
    descargar_y_preparar_videos(duracion + 3)
    procesar_video(duracion, tiene_musica)
    subir_a_youtube(datos)
    print("\n✅ ¡Short publicado!")


if __name__ == "__main__":
    tema = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else random.choice(NICHOS_DEFAULT)
    if len(sys.argv) == 1:
        print("ℹ️  Tema aleatorio")
    asyncio.run(fabricar_video(tema))
