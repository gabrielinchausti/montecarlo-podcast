#!/usr/bin/env python3
"""
procesar_audio.py
Transcribe 1 hora de audio, encuentra el inicio del informativo
y corta exactamente esos 5 minutos.
"""

import os
import sys
import json
import subprocess
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

AUDIO_INPUT  = sys.argv[1]   # archivo de 1 hora
AUDIO_OUTPUT = sys.argv[2]   # archivo de 5 minutos resultante
DURACION     = 300           # 5 minutos en segundos

SEÑAL = """
Llega el más importante contacto con la noticia. 
Diario oral en Monte Carlo.
"""

def transcribir(archivo):
    print("Transcribiendo con Whisper...")
    with open(archivo, "rb") as f:
        respuesta = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )
    return respuesta

def encontrar_timecode(transcripcion):
    print("Buscando inicio del informativo con GPT-4o...")
    
    # Armar texto con timecodes
    segmentos = ""
    for seg in transcripcion.segments:
        inicio = seg["start"]
        texto  = seg["text"]
        minutos = int(inicio // 60)
        segundos = int(inicio % 60)
        segmentos += f"[{minutos:02d}:{segundos:02d}] {texto}\n"
    
    prompt = f"""Tenés la transcripción de 1 hora de Radio Montecarlo Uruguay con timecodes.
    
Buscá el momento exacto donde empieza el informativo de la mañana. 
Se identifica por una cortina musical seguida de frases como:
"{SEÑAL}"

Transcripción:
{segmentos}

Respondé ÚNICAMENTE con un JSON así:
{{"timecode_segundos": 1234, "texto_encontrado": "frase que encontraste"}}

Si no encontrás el informativo, respondé:
{{"timecode_segundos": null, "texto_encontrado": null}}
"""

    respuesta = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    
    resultado = json.loads(respuesta.choices[0].message.content)
    return resultado

def cortar_audio(input_file, output_file, inicio_segundos):
    print(f"Cortando audio desde {inicio_segundos}s por {DURACION}s...")
    cmd = [
        "ffmpeg",
        "-i", input_file,
        "-ss", str(inicio_segundos),
        "-t", str(DURACION),
        "-acodec", "libmp3lame",
        "-ab", "128k",
        "-y",
        output_file
    ]
    subprocess.run(cmd, check=True)
    print(f"Audio cortado: {output_file}")

def main():
    # 1. Transcribir
    transcripcion = transcribir(AUDIO_INPUT)
    
    # 2. Encontrar timecode
    resultado = encontrar_timecode(transcripcion)
    print(f"Resultado: {resultado}")
    
    timecode = resultado.get("timecode_segundos")
    texto    = resultado.get("texto_encontrado")
    
    if timecode is None:
        print("ERROR: No se encontró el informativo en el audio.")
        sys.exit(1)
    
    print(f"Informativo encontrado en: {timecode}s — '{texto}'")
    
    # 3. Cortar
    cortar_audio(AUDIO_INPUT, AUDIO_OUTPUT, timecode)
    print("Listo!")

if __name__ == "__main__":
    main()