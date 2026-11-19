import os
import json
import random
import math
from datetime import datetime

# ==================================================
# EINSTELLUNGEN
# ==================================================

WETTER_PFAD    = os.path.join("Daten", "wetterdaten.json")
AUSGABE_ORDNER = os.path.join("Daten", "sensoren")
ZUFALLS_SEED   = 42

# ==================================================
# STANDORTE  (gleiche Hardware, anderes Mikroklima)
# ==================================================

STANDORTE = {
    "Marktplatz": {
        "temp_offset_tag":   +1.5,
        "temp_offset_nacht": +0.8,
        "temp_daempfung":    0.95,
        "feuchte_faktor":    0.92,
        "feuchte_offset":    -3.0,
        "wind_faktor":       1.15,
        "licht_faktor":      1.00,
        "regen_faktor":      0.95,
        "traegheit":         0.85,
        "rauschen_skala":    1.0,
    },
    "Baumgruppe": {
        "temp_offset_tag":   -1.8,
        "temp_offset_nacht": -0.5,
        "temp_daempfung":    0.80,
        "feuchte_faktor":    1.08,
        "feuchte_offset":    +6.0,
        "wind_faktor":       0.60,
        "licht_faktor":      0.65,
        "regen_faktor":      1.10,
        "traegheit":         0.90,
        "rauschen_skala":    1.2,
    },
    "Flussufer": {
        "temp_offset_tag":   -0.8,
        "temp_offset_nacht": +0.3,
        "temp_daempfung":    0.88,
        "feuchte_faktor":    1.12,
        "feuchte_offset":    +8.0,
        "wind_faktor":       1.10,
        "licht_faktor":      1.05,
        "regen_faktor":      1.05,
        "traegheit":         0.92,
        "rauschen_skala":    0.9,
    },
    "Dachgarten": {
        "temp_offset_tag":   -0.3,
        "temp_offset_nacht": -1.2,
        "temp_daempfung":    1.10,
        "feuchte_faktor":    0.95,
        "feuchte_offset":    -2.0,
        "wind_faktor":       1.45,
        "licht_faktor":      1.05,
        "regen_faktor":      0.90,
        "traegheit":         0.75,
        "rauschen_skala":    1.3,
    },
    "Innenhof": {
        "temp_offset_tag":   +0.5,
        "temp_offset_nacht": +0.6,
        "temp_daempfung":    0.75,
        "feuchte_faktor":    1.05,
        "feuchte_offset":    +4.0,
        "wind_faktor":       0.40,
        "licht_faktor":      0.50,
        "regen_faktor":      1.15,
        "traegheit":         0.93,
        "rauschen_skala":    0.8,
    },
}

# ==================================================
# HARDWARE-RAUSCHEN (für alle Sensoren identisch)
# ==================================================

RAUSCHEN = {
    "temperatur":        0.30,
    "luftfeuchtigkeit":  1.5,
    "luftdruck":         0.8,
    "windgeschwindigkeit": 1.5,
    "niederschlag":      0.15,
    "schneefall":        0.10,
    "bewoelkung":        2.0,
    "uv_index":          0.2,
}

AUSREISSER_WAHRSCHEIN = {
    "temperatur":        0.002,
    "luftfeuchtigkeit":  0.002,
    "luftdruck":         0.001,
    "windgeschwindigkeit": 0.004,
    "niederschlag":      0.001,
    "schneefall":        0.001,
    "bewoelkung":        0.001,
    "uv_index":          0.001,
}

# ==================================================
# HILFSFUNKTIONEN
# ==================================================

def lade_wetterdaten(pfad):
    if not os.path.exists(pfad):
        raise FileNotFoundError(f"Wetterdaten nicht gefunden: {pfad}")
    with open(pfad, "r", encoding="utf-8") as f:
        daten = json.load(f)
    print(f"[OK] {len(daten)} Wettertage geladen.")
    return daten


def begrenze(x, lo, hi):
    return max(lo, min(hi, x))


def tageszeit_faktor(zeile):
    """0 = Nacht, 1 = volle Sonne (Mittag), aus UV-Index."""
    uv = float(zeile.get("uv_index", 0))
    return min(1.0, uv / 8.0)


def wetter_text(bewoelkung, niederschlag, temperatur):
    """Wetterbeschreibung anhand der (Standort-)Werte neu bestimmen."""
    if niederschlag > 5.0:
        return "Starkregen" if niederschlag > 15 else "Regen"
    if niederschlag > 0.1 and temperatur < 1.0:
        return "Schneefall"
    if niederschlag > 0.1:
        return "Leichter Regen"
    if bewoelkung >= 85:
        return "Bedeckt"
    if bewoelkung >= 60:
        return "Stark bewölkt"
    if bewoelkung >= 30:
        return "Teilweise bewölkt"
    return "Klar"


def windrichtung_verschieben(richtung, delta_grad):
    """Windrichtung um delta Grad drehen (Standort-Effekt)."""
    richtungen = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]
    if richtung not in richtungen:
        return richtung
    idx = richtungen.index(richtung)
    verschiebung = int(round(delta_grad / 45.0))
    return richtungen[(idx + verschiebung) % 8]


def simulierte_zeile(zeile, standort, standort_name, tag_index, rng):
    """Erzeugt einen Sensor-Datensatz im gleichen Format wie wetterdaten.json."""
    # --- Tageszeit ---
    tag = tageszeit_faktor(zeile)

    # --- Temperatur ---
    t_orig = float(zeile["temperatur"])
    offset = (standort["temp_offset_tag"] * tag
              + standort["temp_offset_nacht"] * (1 - tag))
    t = 12.0 + (t_orig - 12.0) * standort["temp_daempfung"] + offset
    t += rng.gauss(0, RAUSCHEN["temperatur"] * standort["rauschen_skala"])
    t = round(begrenze(t, -25, 45), 1)

    # --- Luftfeuchtigkeit ---
    f = float(zeile["luftfeuchtigkeit"]) * standort["feuchte_faktor"] + standort["feuchte_offset"]
    f += rng.gauss(0, RAUSCHEN["luftfeuchtigkeit"] * standort["rauschen_skala"])
    f = round(begrenze(f, 0, 100))

    # --- Luftdruck (großräumig, kaum Standort-Effekt) ---
    p = float(zeile["luftdruck"])
    p += rng.gauss(0, RAUSCHEN["luftdruck"] * standort["rauschen_skala"])
    p = round(begrenze(p, 950, 1060), 1)

    # --- Windgeschwindigkeit ---
    wg = float(zeile["windgeschwindigkeit"]) * standort["wind_faktor"]
    wg += rng.gauss(0, RAUSCHEN["windgeschwindigkeit"] * standort["rauschen_skala"])
    wg = round(begrenze(wg, 0, 120), 1)

    # --- Windrichtung (leicht gedreht je nach Standort) ---
    wind_drehung = rng.gauss(0, 15)  # Grad Rauschen
    wr = windrichtung_verschieben(zeile.get("windrichtung", "N"), wind_drehung)

    # --- Niederschlag ---
    n = float(zeile["niederschlag"]) * standort["regen_faktor"]
    n += abs(rng.gauss(0, RAUSCHEN["niederschlag"] * standort["rauschen_skala"]))
    n = round(begrenze(n, 0, 80), 1)

    # --- Schneefall ---
    sch = float(zeile.get("schneefall", 0.0)) * standort["regen_faktor"]
    sch += abs(rng.gauss(0, RAUSCHEN["schneefall"] * standort["rauschen_skala"]))
    sch = round(begrenze(sch, 0, 50), 1)

    # --- Bewölkung (Standort: Baumgruppe/Innenhof sehen weniger Himmel) ---
    bew = float(zeile["bewoelkung"])
    # Schatten-Standorte "sehen" weniger offenen Himmel → scheinbar weniger Wolken
    if standort["licht_faktor"] < 0.7:
        bew *= 0.85
    bew += rng.gauss(0, RAUSCHEN["bewoelkung"] * standort["rauschen_skala"])
    bew = round(begrenze(bew, 0, 100))

    # --- UV-Index (stark vom Lichtfaktor abhängig) ---
    uv = float(zeile.get("uv_index", 0)) * standort["licht_faktor"]
    uv += rng.gauss(0, RAUSCHEN["uv_index"] * standort["rauschen_skala"])
    uv = round(begrenze(uv, 0, 12), 1)

    # --- Wettertext neu bestimmen ---
    wt = wetter_text(bew, n, t)

    # --- Ausreißer (defekte Messung) ---
    if rng.random() < AUSREISSER_WAHRSCHEIN["temperatur"]:
        t = round(rng.uniform(-15, 45), 1)
    if rng.random() < AUSREISSER_WAHRSCHEIN["windgeschwindigkeit"]:
        wg = round(rng.uniform(0, 120), 1)

    return {
        "datum":              zeile["datum"],
        "tag_im_jahr":        zeile["tag_im_jahr"],
        "ort":                standort_name,
        "jahreszeit":         zeile["jahreszeit"],
        "wetterlage":         zeile["wetterlage"],
        "temperatur":         t,
        "luftfeuchtigkeit":   f,
        "luftdruck":          p,
        "windgeschwindigkeit": wg,
        "windrichtung":       wr,
        "niederschlag":       n,
        "schneefall":         sch,
        "bewoelkung":         bew,
        "uv_index":           uv,
        "wetter":             wt,
    }


# ==================================================
# MAIN
# ==================================================

def main():
    rng = random.Random(ZUFALLS_SEED)
    wetterdaten = lade_wetterdaten(WETTER_PFAD)
    os.makedirs(AUSGABE_ORDNER, exist_ok=True)

    gesamt = []

    for standort_name, standort in STANDORTE.items():
        daten = [
            simulierte_zeile(zeile, standort, standort_name, i, rng)
            for i, zeile in enumerate(wetterdaten)
        ]

        pfad = os.path.join(AUSGABE_ORDNER, f"sensor_{standort_name}.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=4)
        print(f"[{standort_name:>11}] {len(daten):>5} Tage -> {pfad}")

        gesamt.extend(daten)

    # Kombinierte Datei
    kombi_pfad = os.path.join(AUSGABE_ORDNER, "sensoren_alle.json")
    with open(kombi_pfad, "w", encoding="utf-8") as f:
        json.dump(gesamt, f, ensure_ascii=False, indent=4)
    print(f"\nKombiniert: {kombi_pfad}  ({len(gesamt)} Datensätze)")

    # Beispielausgabe zeigen
    print("\n--- Beispiel: erster Tag pro Standort ---")
    for standort_name in STANDORTE:
        pfad = os.path.join(AUSGABE_ORDNER, f"sensor_{standort_name}.json")
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)[0]
        print(f"{standort_name:>11}: {d['temperatur']:>5} °C, "
              f"{d['luftfeuchtigkeit']:>3} %, "
              f"{d['windgeschwindigkeit']:>4} km/h, "
              f"{d['wetter']}")


if __name__ == "__main__":
    main()