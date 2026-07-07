#!/usr/bin/env python3
import os
import glob
from datetime import datetime

BASE_URL   = "https://gabrielinchausti.github.io/montecarlo-podcast/audio"
FEED_TITLE = "Radio Montecarlo – Noticias"
FEED_DESC  = "Grabaciones de Radio Montecarlo CX20 930 AM, Uruguay."
FEED_LINK  = "https://www.radiomontecarlo.com.uy"
FEED_LANG  = "es-uy"
FEED_IMG   = "https://www.radiomontecarlo.com.uy/artworks/artworks_radiomontecarlocomuy/logos/logo_social.jpg"

def archivo_to_item(nombre):
    # nombre = "episodio-2026-07-03-0629"
    partes = nombre.replace("episodio-", "").split("-")
    fecha  = "-".join(partes[:3])
    hora   = partes[3] if len(partes) > 3 else "0000"
    hora_display = f"{hora[:2]}:{hora[2:]}"
    mp3_url = f"{BASE_URL}/{nombre}.mp3"

    try:
        dt       = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H%M")
        pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S -0300")
    except ValueError:
        pub_date = fecha

    return f"""
    <item>
      <title>Montecarlo {hora_display} – {fecha}</title>
      <description>Grabación de Radio Montecarlo CX20 930 AM del {fecha} a las {hora_display}</description>
      <pubDate>{pub_date}</pubDate>
      <enclosure url="{mp3_url}" type="audio/mpeg" length="0"/>
      <guid isPermaLink="false">{mp3_url}</guid>
      <itunes:duration>10:00</itunes:duration>
      <itunes:explicit>no</itunes:explicit>
    </item>"""

def build_feed(items_xml):
    now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{FEED_TITLE}</title>
    <link>{FEED_LINK}</link>
    <description>{FEED_DESC}</description>
    <language>{FEED_LANG}</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>Radio Montecarlo CX20 930 AM</itunes:author>
    <itunes:category text="News"/>
    <itunes:image href="{FEED_IMG}"/>
    <itunes:explicit>no</itunes:explicit>
    {items_xml}
  </channel>
</rss>
"""

def main():
    print("Leyendo archivos de audio/...")
    archivos = sorted(glob.glob("audio/episodio-*.mp3"), reverse=True)
    print(f"  → {len(archivos)} episodios encontrados")

    nombres   = [os.path.basename(a).replace(".mp3", "") for a in archivos]
    items_xml = "".join(archivo_to_item(n) for n in nombres)
    feed      = build_feed(items_xml)

    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(feed)
    print("feed.xml generado correctamente.")

if __name__ == "__main__":
    main()