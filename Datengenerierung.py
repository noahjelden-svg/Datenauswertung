import os
import json
import random
import math

from datetime import datetime, timedelta


# ==================================================
# EINSTELLUNGEN
# ==================================================

ANZAHL_TAGE = 365 * 5
START_DATUM = "2021-01-01"

ORT = "Heidelberg"

SPEICHER_ORDNER = "Daten"

ZUFALLS_SEED = 42

# Grundtemperaturen der Jahreszeiten
JAHRESZEITEN = {
    "Winter": {"temperatur": 3, "regen": 0.30},
    "Frühling": {"temperatur": 12, "regen": 0.30},
    "Sommer": {"temperatur": 22, "regen": 0.20},
    "Herbst": {"temperatur": 11, "regen": 0.35}
}

# Wetterlagen und ihre Übergangswahrscheinlichkeiten
# Jede Zeile beschreibt, was morgen passieren kann.

UEBERGAENGE = {
    "Hochdruck": {
        "Hochdruck": 0.75,
        "Wechselhaft": 0.20,
        "Regenfront": 0.05
    },

    "Wechselhaft": {
        "Hochdruck": 0.25,
        "Wechselhaft": 0.50,
        "Regenfront": 0.25
    },

    "Regenfront": {
        "Hochdruck": 0.15,
        "Wechselhaft": 0.35,
        "Regenfront": 0.50
    }
}

# Wahrscheinlichkeit für Regen je Wetterlage
REGEN_WAHRSCHEINLICHKEIT = {
    "Hochdruck": 0.05,
    "Wechselhaft": 0.40,
    "Regenfront": 0.80
}


# ==================================================
# INITIALISIERUNG
# ==================================================

random.seed(ZUFALLS_SEED)

os.makedirs(SPEICHER_ORDNER, exist_ok=True)


# ==================================================
# HILFSFUNKTIONEN
# ==================================================

def begrenzen(wert, minimum, maximum):
    return max(minimum, min(maximum, wert))


def jahreszeit_berechnen(monat):

    if monat in [12, 1, 2]:
        return "Winter"

    if monat in [3, 4, 5]:
        return "Frühling"

    if monat in [6, 7, 8]:
        return "Sommer"

    return "Herbst"


def naechste_wetterlage(aktuell):

    moeglichkeiten = UEBERGAENGE[aktuell]

    return random.choices(
        list(moeglichkeiten.keys()),
        weights=list(moeglichkeiten.values()),
        k=1
    )[0]


# ==================================================
# WETTERGENERATOR
# ==================================================

def generiere_wetter(datum, vorherige_daten, zustand):

    tag_im_jahr = datum.timetuple().tm_yday

    jahreszeit = jahreszeit_berechnen(datum.month)

    grundwerte = JAHRESZEITEN[jahreszeit]

    # ----------------------------------------------
    # 1. WETTERLAGE
    # ----------------------------------------------

    if vorherige_daten is not None:
        zustand = naechste_wetterlage(zustand)

    # ----------------------------------------------
    # 2. TEMPERATUR
    # ----------------------------------------------

    # Saisonale Temperaturkurve
    saison = math.cos(
        2 * math.pi * (tag_im_jahr - 200) / 365
    )

    saisonale_temperatur = (
        12 + 10 * saison
    )

    # Wetterlagen beeinflussen die Temperatur
    temperatur_einfluss = {
        "Hochdruck": 2.0,
        "Wechselhaft": 0.0,
        "Regenfront": -2.5
    }

    # Temperatur entwickelt sich langsam
    if vorherige_daten is None:
        temperatur_abweichung = random.gauss(0, 2)

    else:
        alte_temperatur = vorherige_daten["temperatur"]

        alte_saison = (
            12 + 10 * math.cos(
                2 * math.pi *
                (vorherige_daten["tag_im_jahr"] - 200) / 365
            )
        )

        alte_abweichung = alte_temperatur - alte_saison

        temperatur_abweichung = (
            alte_abweichung * 0.80
            + random.gauss(0, 1.5)
        )

    temperatur = (
        saisonale_temperatur
        + temperatur_abweichung
        + temperatur_einfluss[zustand]
    )

    temperatur = round(
        begrenzen(temperatur, -15, 40), 1
    )

    # ----------------------------------------------
    # 3. LUFTDRUCK
    # ----------------------------------------------

    druck_einfluss = {
        "Hochdruck": 12,
        "Wechselhaft": 0,
        "Regenfront": -12
    }

    if vorherige_daten is None:
        luftdruck = 1013

    else:
        luftdruck = (
            vorherige_daten["luftdruck"] * 0.70
            + 1013 * 0.30
        )

    luftdruck += druck_einfluss[zustand]

    luftdruck = round(
        begrenzen(
            luftdruck + random.gauss(0, 2),
            970, 1045
        ), 1
    )

    # ----------------------------------------------
    # 4. BEWÖLKUNG
    # ----------------------------------------------

    wolken_grundwert = {
        "Hochdruck": 15,
        "Wechselhaft": 55,
        "Regenfront": 90
    }

    bewoelkung = round(
        begrenzen(
            random.gauss(
                wolken_grundwert[zustand], 15
            ), 0, 100
        )
    )

    # ----------------------------------------------
    # 5. REGEN
    # ----------------------------------------------

    regen_chance = REGEN_WAHRSCHEINLICHKEIT[zustand]

    # Regenperioden bleiben wahrscheinlicher,
    # wenn es bereits gestern geregnet hat.

    if vorherige_daten is not None:

        if vorherige_daten["niederschlag"] > 0:
            regen_chance += 0.12

    # Wolken beeinflussen Regenwahrscheinlichkeit
    regen_chance += (bewoelkung / 100) * 0.10

    regen_chance = begrenzen(
        regen_chance, 0, 0.95
    )

    if random.random() < regen_chance:

        niederschlag = random.gammavariate(
            2.0, 2.5
        )

        # Bei einer Regenfront stärkere Niederschläge
        if zustand == "Regenfront":
            niederschlag *= random.uniform(1.0, 2.0)

    else:
        niederschlag = 0.0

    niederschlag = round(
        min(niederschlag, 80), 1
    )

    # ----------------------------------------------
    # 6. LUFTFEUCHTIGKEIT
    # ----------------------------------------------

    luftfeuchtigkeit = (
        35
        + bewoelkung * 0.45
        + niederschlag * 1.2
        + random.gauss(0, 5)
    )

    luftfeuchtigkeit = round(
        begrenzen(luftfeuchtigkeit, 20, 100)
    )

    # ----------------------------------------------
    # 7. WIND
    # ----------------------------------------------

    wind_grundwert = {
        "Hochdruck": 6,
        "Wechselhaft": 12,
        "Regenfront": 25
    }

    wind = random.gauss(
        wind_grundwert[zustand], 5
    )

    wind = round(
        begrenzen(wind, 0, 100), 1
    )

    windrichtungen = [
        "N", "NO", "O", "SO",
        "S", "SW", "W", "NW"
    ]

    windrichtung = random.choice(windrichtungen)

    # ----------------------------------------------
    # 8. SCHNEEFALL
    # ----------------------------------------------

    schneefall = 0.0

    if temperatur <= 1 and niederschlag > 0:

        schneefall = round(
            niederschlag * random.uniform(0.5, 1.5), 1
        )

        niederschlag = 0.0

    # ----------------------------------------------
    # 9. UV-INDEX
    # ----------------------------------------------

    uv_index = round(
        begrenzen(
            8 * max(0, saison)
            * (1 - bewoelkung / 120),
            0, 11
        )
    )

    # ----------------------------------------------
    # 10. WETTERBESCHREIBUNG
    # ----------------------------------------------

    if schneefall > 0:
        wetter = "Schnee"

    elif niederschlag >= 10:
        wetter = "Starker Regen"

    elif niederschlag > 0:
        wetter = "Regen"

    elif bewoelkung >= 75:
        wetter = "Stark bewölkt"

    elif bewoelkung >= 40:
        wetter = "Teilweise bewölkt"

    else:
        wetter = "Sonnig"

    # ----------------------------------------------
    # 11. DATENSATZ
    # ----------------------------------------------

    daten = {

        "datum": datum.strftime("%Y-%m-%d"),

        "tag_im_jahr": tag_im_jahr,

        "ort": ORT,

        "jahreszeit": jahreszeit,

        "wetterlage": zustand,

        "temperatur": temperatur,

        "luftfeuchtigkeit": luftfeuchtigkeit,

        "luftdruck": luftdruck,

        "windgeschwindigkeit": wind,

        "windrichtung": windrichtung,

        "niederschlag": niederschlag,

        "schneefall": schneefall,

        "bewoelkung": bewoelkung,

        "uv_index": uv_index,

        "wetter": wetter
    }

    return daten, zustand


# ==================================================
# HAUPTPROGRAMM
# ==================================================

def hauptprogramm():

    start = datetime.strptime(
        START_DATUM, "%Y-%m-%d"
    )

    alle_daten = []

    vorherige_daten = None

    wetterlage = "Wechselhaft"

    print("Generiere Wetterdaten...")

    for tag in range(ANZAHL_TAGE):

        datum = start + timedelta(days=tag)

        daten, wetterlage = generiere_wetter(
            datum,
            vorherige_daten,
            wetterlage
        )

        alle_daten.append(daten)

        vorherige_daten = daten

    # JSON speichern

    dateipfad = os.path.join(
        SPEICHER_ORDNER,
        "wetterdaten.json"
    )

    with open(
        dateipfad, "w", encoding="utf-8"
    ) as datei:

        json.dump(
            alle_daten,
            datei,
            indent=4,
            ensure_ascii=False
        )

    # Statistik erstellen

    regentage = sum(
        1 for tag in alle_daten
        if tag["niederschlag"] > 0
    )

    durchschnitt = sum(
        tag["temperatur"] for tag in alle_daten
    ) / len(alle_daten)

    print("\n================================")
    print("WETTERDATEN ERFOLGREICH ERSTELLT")
    print("================================")

    print(f"Ort: {ORT}")
    print(f"Tage: {ANZAHL_TAGE}")
    print(f"Regentage: {regentage}")
    print(f"Durchschnittstemperatur: {durchschnitt:.1f} °C")
    print(f"Speicherort: {dateipfad}")


if __name__ == "__main__":
    hauptprogramm()