"""Build the small offline fallback catalog shipped with Radio Atlas.

These are a curated sample of stations with public streams, kept only so the
app remains browsable when Radio Browser cannot be reached. The live directory
is always the primary source.
"""

from __future__ import annotations

import json
from pathlib import Path

# (slug, name, stream, country, code, city, lat, lon, tags, codec, bitrate, clicks)
STATIONS = [
    # United States
    ("soma-groove-salad", "SomaFM Groove Salad", "https://ice1.somafm.com/groovesalad-128-mp3", "United States", "US", "San Francisco", 37.7749, -122.4194, "ambient,downtempo,electronic", "MP3", 128, 92000),
    ("soma-drone-zone", "SomaFM Drone Zone", "https://ice1.somafm.com/dronezone-128-mp3", "United States", "US", "San Francisco", 37.7751, -122.4182, "ambient,drone,chillout", "MP3", 128, 61000),
    ("soma-deep-space-one", "SomaFM Deep Space One", "https://ice1.somafm.com/deepspaceone-128-mp3", "United States", "US", "San Francisco", 37.7753, -122.4171, "ambient,space,electronic", "MP3", 128, 38000),
    ("soma-indie-pop", "SomaFM Indie Pop Rocks", "https://ice1.somafm.com/indiepop-128-mp3", "United States", "US", "San Francisco", 37.7756, -122.4160, "indie,pop,alternative", "MP3", 128, 41000),
    ("soma-secret-agent", "SomaFM Secret Agent", "https://ice1.somafm.com/secretagent-128-mp3", "United States", "US", "San Francisco", 37.7758, -122.4150, "lounge,spy jazz", "MP3", 128, 29000),
    ("soma-beat-blender", "SomaFM Beat Blender", "https://ice1.somafm.com/beatblender-128-mp3", "United States", "US", "San Francisco", 37.7760, -122.4140, "deep house,electronic", "MP3", 128, 27000),
    ("soma-defcon", "SomaFM DEF CON Radio", "https://ice1.somafm.com/defcon-128-mp3", "United States", "US", "San Francisco", 37.7762, -122.4130, "electronic,hacker", "MP3", 128, 24000),
    ("soma-u80s", "SomaFM Underground 80s", "https://ice1.somafm.com/u80s-128-mp3", "United States", "US", "San Francisco", 37.7764, -122.4120, "80s,synthpop,new wave", "MP3", 128, 33000),
    ("radio-paradise", "Radio Paradise", "https://stream.radioparadise.com/mp3-192", "United States", "US", "Paradise", 39.7596, -121.6219, "eclectic,rock", "MP3", 192, 88000),
    ("radio-paradise-mellow", "Radio Paradise Mellow Mix", "https://stream.radioparadise.com/mellow-192", "United States", "US", "Paradise", 39.7598, -121.6210, "chillout,eclectic", "MP3", 192, 36000),
    ("radio-paradise-rock", "Radio Paradise Rock Mix", "https://stream.radioparadise.com/rock-192", "United States", "US", "Paradise", 39.7600, -121.6200, "rock,eclectic", "MP3", 192, 30000),
    ("radio-paradise-global", "Radio Paradise Global Mix", "https://stream.radioparadise.com/global-192", "United States", "US", "Paradise", 39.7602, -121.6190, "world,eclectic", "MP3", 192, 26000),
    ("wfmu", "WFMU", "https://stream0.wfmu.org/freeform-128k", "United States", "US", "Jersey City", 40.7178, -74.0431, "freeform,experimental", "MP3", 128, 47000),
    ("npr-news", "NPR News", "https://npr-ice.streamguys1.com/live.mp3", "United States", "US", "Washington", 38.9072, -77.0369, "news,public radio", "MP3", 128, 84000),
    ("wnyc", "WNYC", "https://fm939.wnyc.org/wnycfm", "United States", "US", "New York", 40.7128, -74.0060, "news,public radio", "MP3", 128, 52000),
    ("kexp", "KEXP 90.3", "https://kexp.streamguys1.com/kexp160.aac", "United States", "US", "Seattle", 47.6062, -122.3321, "indie,alternative,public radio", "AAC", 160, 55000),
    # Canada
    ("cbc-toronto", "CBC Radio One Toronto", "https://cbcradiolive.akamaized.net/hls/live/2041053/ES_R1_TOR/master.m3u8", "Canada", "CA", "Toronto", 43.6532, -79.3832, "news,public radio", "AAC", 128, 43000),
    ("cbc-montreal", "CBC Radio One Montreal", "https://cbcradiolive.akamaized.net/hls/live/2041053/ES_R1_MTL/master.m3u8", "Canada", "CA", "Montreal", 45.5019, -73.5674, "news,public radio", "AAC", 128, 31000),
    ("cbc-vancouver", "CBC Radio One Vancouver", "https://cbcradiolive.akamaized.net/hls/live/2041053/ES_R1_VAN/master.m3u8", "Canada", "CA", "Vancouver", 49.2827, -123.1207, "news,public radio", "AAC", 128, 29000),
    # United Kingdom & Ireland
    ("bbc-6music", "BBC Radio 6 Music", "https://stream.live.vc.bbcmedia.co.uk/bbc_6music", "United Kingdom", "GB", "London", 51.5074, -0.1278, "alternative,indie", "MP3", 128, 79000),
    ("bbc-radio4", "BBC Radio 4", "https://stream.live.vc.bbcmedia.co.uk/bbc_radio_fourfm", "United Kingdom", "GB", "London", 51.5076, -0.1272, "talk,news,drama", "MP3", 128, 72000),
    ("bbc-world", "BBC World Service", "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service", "United Kingdom", "GB", "London", 51.5078, -0.1266, "news,world", "MP3", 128, 68000),
    ("nts-1", "NTS Radio 1", "https://stream-relay-geo.ntslive.net/stream", "United Kingdom", "GB", "London", 51.5080, -0.1260, "eclectic,underground", "MP3", 128, 44000),
    ("nts-2", "NTS Radio 2", "https://stream-relay-geo.ntslive.net/stream2", "United Kingdom", "GB", "London", 51.5082, -0.1254, "eclectic,underground", "MP3", 128, 33000),
    ("rte-radio1", "RTÉ Radio 1", "https://av.rasset.ie/av/live/radio/radio1.m3u8", "Ireland", "IE", "Dublin", 53.3498, -6.2603, "news,talk,public radio", "AAC", 128, 27000),
    ("rte-2fm", "RTÉ 2FM", "https://av.rasset.ie/av/live/radio/2fm.m3u8", "Ireland", "IE", "Dublin", 53.3500, -6.2597, "pop,rock", "AAC", 128, 22000),
    # France
    ("fip", "FIP", "https://icecast.radiofrance.fr/fip-midfi.mp3", "France", "FR", "Paris", 48.8566, 2.3522, "eclectic,jazz,world", "MP3", 128, 81000),
    ("fip-jazz", "FIP Jazz", "https://icecast.radiofrance.fr/fipjazz-midfi.mp3", "France", "FR", "Paris", 48.8568, 2.3528, "jazz", "MP3", 128, 34000),
    ("fip-groove", "FIP Groove", "https://icecast.radiofrance.fr/fipgroove-midfi.mp3", "France", "FR", "Paris", 48.8570, 2.3534, "funk,groove,soul", "MP3", 128, 29000),
    ("fip-rock", "FIP Rock", "https://icecast.radiofrance.fr/fiprock-midfi.mp3", "France", "FR", "Paris", 48.8572, 2.3540, "rock", "MP3", 128, 28000),
    ("france-inter", "France Inter", "https://icecast.radiofrance.fr/franceinter-midfi.mp3", "France", "FR", "Paris", 48.8574, 2.3546, "news,talk,public radio", "MP3", 128, 76000),
    ("france-musique", "France Musique", "https://icecast.radiofrance.fr/francemusique-midfi.mp3", "France", "FR", "Paris", 48.8576, 2.3552, "classical", "MP3", 128, 39000),
    ("france-culture", "France Culture", "https://icecast.radiofrance.fr/franceculture-midfi.mp3", "France", "FR", "Paris", 48.8578, 2.3558, "culture,talk", "MP3", 128, 36000),
    ("mouv", "Mouv'", "https://icecast.radiofrance.fr/mouv-midfi.mp3", "France", "FR", "Paris", 48.8580, 2.3564, "hip hop,urban", "MP3", 128, 25000),
    # Germany
    ("dlf", "Deutschlandfunk", "https://st01.sslstream.dlf.de/dlf/01/128/mp3/stream.mp3", "Germany", "DE", "Berlin", 52.5200, 13.4050, "news,culture,public radio", "MP3", 128, 46000),
    ("dlf-kultur", "Deutschlandfunk Kultur", "https://st02.sslstream.dlf.de/dlf/02/128/mp3/stream.mp3", "Germany", "DE", "Berlin", 52.5202, 13.4056, "culture,talk", "MP3", 128, 31000),
    ("radioeins", "radioeins", "https://dispatcher.rndfnk.com/rbb/radioeins/live/mp3/128/stream.mp3", "Germany", "DE", "Berlin", 52.5204, 13.4062, "eclectic,indie", "MP3", 128, 26000),
    ("1live", "1LIVE", "https://wdr-1live-live.icecast.wdr.de/wdr/1live/live/mp3/128/stream.mp3", "Germany", "DE", "Cologne", 50.9375, 6.9603, "pop,rock,alternative", "MP3", 128, 48000),
    ("ndr2", "NDR 2", "https://dispatcher.rndfnk.com/ndr/ndr2/hamburg/mp3/128/stream.mp3", "Germany", "DE", "Hamburg", 53.5511, 9.9937, "pop,rock", "MP3", 128, 33000),
    ("bayern3", "Bayern 3", "https://dispatcher.rndfnk.com/br/br3/live/mp3/mid", "Germany", "DE", "Munich", 48.1351, 11.5820, "pop,rock", "MP3", 128, 35000),
    # Iberia
    ("los40", "LOS40", "https://playerservices.streamtheworld.com/api/livestream-redirect/LOS40AAC.aac", "Spain", "ES", "Madrid", 40.4168, -3.7038, "pop,hits", "AAC", 64, 67000),
    ("cadena-ser", "Cadena SER", "https://playerservices.streamtheworld.com/api/livestream-redirect/CADENASERAAC.aac", "Spain", "ES", "Madrid", 40.4170, -3.7030, "news,talk", "AAC", 64, 54000),
    ("flaix-fm", "Flaix FM", "https://stream.flaixfm.cat/flaixfm", "Spain", "ES", "Barcelona", 41.3874, 2.1686, "electronic,dance", "MP3", 128, 24000),
    ("antena3", "Antena 3", "https://streaming-live.rtp.pt/liveradio/antena380a/playlist.m3u8", "Portugal", "PT", "Lisbon", 38.7223, -9.1393, "pop,news", "AAC", 128, 21000),
    ("rfm-portugal", "RFM", "https://playerservices.streamtheworld.com/api/livestream-redirect/RFMAAC.aac", "Portugal", "PT", "Lisbon", 38.7225, -9.1387, "pop,rock", "AAC", 64, 25000),
    # Italy & Greece
    ("rai-radio3", "Rai Radio 3", "https://icestreaming.rai.it/3.mp3", "Italy", "IT", "Rome", 41.9028, 12.4964, "classical,culture", "MP3", 128, 30000),
    ("rai-radio1", "Rai Radio 1", "https://icestreaming.rai.it/1.mp3", "Italy", "IT", "Rome", 41.9030, 12.4970, "news,talk", "MP3", 128, 34000),
    ("ert-kosmos", "ERT Kosmos", "https://radiostreaming.ert.gr/ert-kosmos", "Greece", "GR", "Athens", 37.9838, 23.7275, "world,folk", "MP3", 128, 9000),
    # Low countries, Alpine, Nordic
    ("npo-radio2", "NPO Radio 2", "https://icecast.omroep.nl/radio2-bb-mp3", "Netherlands", "NL", "Hilversum", 52.2292, 5.1669, "pop,public radio", "MP3", 128, 39000),
    ("npo-3fm", "NPO 3FM", "https://icecast.omroep.nl/3fm-bb-mp3", "Netherlands", "NL", "Hilversum", 52.2294, 5.1675, "alternative,pop", "MP3", 128, 32000),
    ("stubru", "Studio Brussel", "https://icecast.vrtcdn.be/stubru-high.mp3", "Belgium", "BE", "Brussels", 50.8503, 4.3517, "alternative,indie", "MP3", 128, 35000),
    ("vrt-radio1", "VRT Radio 1", "https://icecast.vrtcdn.be/radio1-high.mp3", "Belgium", "BE", "Brussels", 50.8505, 4.3523, "news,talk", "MP3", 128, 23000),
    ("srf3", "SRF 3", "https://stream.srg-ssr.ch/m/drs3/mp3_128", "Switzerland", "CH", "Zurich", 47.3769, 8.5417, "pop,alternative", "MP3", 128, 28000),
    ("couleur3", "Couleur 3", "https://stream.srg-ssr.ch/m/couleur3/mp3_128", "Switzerland", "CH", "Lausanne", 46.5197, 6.6323, "alternative,electronic", "MP3", 128, 19000),
    ("oe3", "Ö3", "https://orf-live.ors-shoutcast.at/oe3-q2a", "Austria", "AT", "Vienna", 48.2082, 16.3738, "pop,hits", "AAC", 192, 37000),
    ("fm4", "FM4", "https://orf-live.ors-shoutcast.at/fm4-q2a", "Austria", "AT", "Vienna", 48.2084, 16.3744, "alternative,electronic", "AAC", 192, 26000),
    ("sr-p3", "Sveriges Radio P3", "https://sverigesradio.se/topsy/direkt/164-hi-mp3", "Sweden", "SE", "Stockholm", 59.3293, 18.0686, "pop,public radio", "MP3", 192, 31000),
    ("sr-p1", "Sveriges Radio P1", "https://sverigesradio.se/topsy/direkt/132-hi-mp3", "Sweden", "SE", "Stockholm", 59.3295, 18.0692, "news,talk", "MP3", 192, 27000),
    ("dr-p3", "DR P3", "https://live-icy.dr.dk/A/A05H.mp3", "Denmark", "DK", "Copenhagen", 55.6761, 12.5683, "pop,public radio", "MP3", 128, 25000),
    # Central & Eastern Europe
    ("cro-radiozurnal", "ČRo Radiožurnál", "https://rozhlas.stream/radiozurnal_mp3_128.mp3", "Czechia", "CZ", "Prague", 50.0755, 14.4378, "news,talk", "MP3", 128, 24000),
    ("cro-vltava", "ČRo Vltava", "https://rozhlas.stream/vltava_mp3_128.mp3", "Czechia", "CZ", "Prague", 50.0757, 14.4384, "classical,culture", "MP3", 128, 17000),
    ("rmf-fm", "RMF FM", "https://rs6-krk2.rmfstream.pl/RMFFM48", "Poland", "PL", "Kraków", 50.0647, 19.9450, "pop,rock", "MP3", 128, 33000),
    # Middle East & Africa
    ("trt-radyo3", "TRT Radyo 3", "https://radio-trtradyo3.live.trt.com.tr/master.m3u8", "Türkiye", "TR", "Ankara", 39.9334, 32.8597, "classical,jazz", "AAC", 128, 12000),
    ("hit-radio-ma", "Hit Radio", "https://hitradio-maroc.ice.infomaniak.ch/hitradio-maroc-128.mp3", "Morocco", "MA", "Casablanca", 33.5731, -7.5898, "pop,hits", "MP3", 128, 18000),
    ("5fm", "5FM", "https://playerservices.streamtheworld.com/api/livestream-redirect/5FMAAC.aac", "South Africa", "ZA", "Johannesburg", -26.2041, 28.0473, "pop,alternative", "AAC", 64, 22000),
    # Americas, Asia, Oceania
    ("w-radio-co", "W Radio", "https://playerservices.streamtheworld.com/api/livestream-redirect/WRADIOAAC.aac", "Colombia", "CO", "Bogotá", 4.7110, -74.0721, "news,talk", "AAC", 64, 26000),
    ("class-95", "Class 95", "https://playerservices.streamtheworld.com/api/livestream-redirect/CLASS95AAC.aac", "Singapore", "SG", "Singapore", 1.3521, 103.8198, "pop,adult contemporary", "AAC", 64, 16000),
    ("air-fm-rainbow", "AIR FM Rainbow", "https://air.pc.cdn.bitgravity.com/air/live/pbaudio001/playlist.m3u8", "India", "IN", "New Delhi", 28.6139, 77.2090, "bollywood,pop", "AAC", 128, 20000),
    ("triple-j", "Triple J", "https://live-radio01.mediahubaustralia.com/2TJW/mp3/", "Australia", "AU", "Sydney", -33.8688, 151.2093, "alternative,indie", "MP3", 128, 47000),
]


def main() -> None:
    records = []
    for (
        slug,
        name,
        url,
        country,
        code,
        city,
        latitude,
        longitude,
        tags,
        codec,
        bitrate,
        clicks,
    ) in STATIONS:
        records.append(
            {
                "stationuuid": f"seed-{slug}",
                "name": name,
                "url_resolved": url,
                "country": country,
                "countrycode": code,
                "state": city,
                "tags": tags,
                "codec": codec,
                "bitrate": bitrate,
                "votes": max(10, clicks // 8),
                "clickcount": clicks,
                "geo_lat": latitude,
                "geo_long": longitude,
            }
        )
    target = (
        Path(__file__).resolve().parent.parent
        / "radio_atlas"
        / "assets"
        / "seed_stations.json"
    )
    target.write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n")
    print(f"Wrote {len(records)} stations to {target}")


if __name__ == "__main__":
    main()
