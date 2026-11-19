# ==================================================
# IMPORTS
# ==================================================
# os       -> Dateipfade bauen, Ordner erstellen
# json     -> JSON-Dateien lesen/schreiben
# numpy    -> schnelle Zahlen-Arrays (Matrix-Operationen)
# datetime -> Datum parsen (falls nötig)
import os
import json
import numpy as np
from datetime import datetime


# ==================================================
# EINSTELLUNGEN (hier drehst du die Stellschrauben)
# ==================================================

# Wo liegen die Eingabedaten?
SENSOREN_PFAD  = os.path.join("Daten", "sensoren", "sensoren_alle.json")

# Wo soll das trainierte Modell gespeichert werden?
MODELL_ORDNER  = os.path.join("Daten", "modell")

# Was soll die KI vorhersagen?
# Muss ein Feldname aus deinen Daten sein, z.B. "temperatur", "niederschlag"
ZIELGROESSE = "temperatur"

# Wie viele Tage in die Zukunft soll vorhergesagt werden?
# 1 = morgen, 3 = in 3 Tagen, 7 = in einer Woche
HORIZONT_TAGE = 1

# Wie viele vergangene Tage soll das Modell als Eingabe sehen?
# 7 = die letzten 7 Tage werden zu einem flachen Feature-Vektor
FENSTER_TAGE  = 7

# Wie viel Prozent der Daten für den Test zurückhalten?
# 0.2 = die letzten 20 % der Zeit werden zum Testen genutzt
TEST_ANTEIL   = 0.2

# Seed für Reproduzierbarkeit (gleiche Ergebnisse bei jedem Lauf)
ZUFALLS_SEED  = 42

# Welche Messgrößen sollen als Features genutzt werden?
# Alle Felder, die pro Ort als Zahl vorliegen
MESSGROESSEN = [
    "temperatur",
    "luftfeuchtigkeit",
    "luftdruck",
    "windgeschwindigkeit",
    "niederschlag",
    "schneefall",
    "bewoelkung",
    "uv_index",
]


# ==================================================
# HILFSFUNKTIONEN
# ==================================================

def lade_json(pfad):
    """Lädt eine JSON-Datei und gibt den Inhalt (Liste/Dict) zurück."""
    if not os.path.exists(pfad):
        # Klare Fehlermeldung statt kryptischem FileNotFoundError
        raise FileNotFoundError(f"Datei nicht gefunden: {pfad}")
    with open(pfad, "r", encoding="utf-8") as f:
        return json.load(f)


def bereinige_daten(daten):
    """
    Entfernt kaputte Einträge aus der Liste.
    In deinen Daten gab es z.B. ein '{ ['-Artefakt, das kein gültiges
    Dict mit 'datum' und 'ort' ist. Solche Einträge werden übersprungen.
    """
    sauber = []
    for e in daten:
        # Nur Dicts behalten, die die Pflichtfelder haben
        if not isinstance(e, dict):
            continue
        if "datum" not in e or "ort" not in e:
            continue
        sauber.append(e)

    if not sauber:
        raise ValueError("Keine gültigen Einträge nach Bereinigung.")

    # Diagnose-Ausgabe: was ist übrig, welche Orte, welche Felder?
    print(f"Bereinigt: {len(sauber)} von {len(daten)} Einträgen gültig")
    print(f"Gefundene Orte: {sorted({e['ort'] for e in sauber})}")
    print(f"Verfügbare Felder: {sorted(sauber[0].keys())}")
    return sauber


# ==================================================
# FEATURE-MATRIX BAUEN
# ==================================================
# Das ist der Kern: aus den Rohdaten eine Matrix X (Eingabe)
# und einen Vektor y (Ziel) bauen, mit denen sklearn trainieren kann.

def baue_feature_matrix():
    # 1) Daten laden + bereinigen
    daten = bereinige_daten(lade_json(SENSOREN_PFAD))

    # 2) Alle Orte ermitteln (jeder Ort = ein "Sensor-Standort")
    orte = sorted({e["ort"] for e in daten})
    print(f"\nNutze Orte als Sensoren: {orte}")

    # 3) Prüfen, welche Messgrößen wirklich in den Daten stehen
    vorhandene_messgroessen = [m for m in MESSGROESSEN if m in daten[0]]
    fehlende = set(MESSGROESSEN) - set(vorhandene_messgroessen)
    if fehlende:
        print(f"Warnung: fehlende Messgrößen werden ignoriert: {fehlende}")

    # Zielgröße muss vorhanden sein, sonst macht Training keinen Sinn
    if ZIELGROESSE not in vorhandene_messgroessen:
        raise ValueError(
            f"Zielgröße '{ZIELGROESSE}' nicht in Daten. "
            f"Verfügbar: {vorhandene_messgroessen}"
        )

    # 4) Lookup-Tabelle: (datum, ort) -> komplette Zeile
    #    Damit finden wir später schnell "Wert von Ort X an Tag Y"
    zeilen_map = {}
    for e in daten:
        zeilen_map[(e["datum"], e["ort"])] = e

    # 5) Welche Tage haben Daten für ALLE Orte?
    #    Nur diese Tage können wir nutzen (sonst fehlen Features)
    tage_pro_ort = {o: set() for o in orte}
    for (d, o) in zeilen_map:
        tage_pro_ort[o].add(d)
    # Schnittmenge aller Tage über alle Orte
    gemeinsame_tage = sorted(set.intersection(*tage_pro_ort.values()))
    print(f"Gemeinsame Tage über alle Orte: {len(gemeinsame_tage)}")

    # 6) Feature-Namen pro Tag definieren (für spätere Interpretation)
    #    Pro Tag: für jeden Ort jede Messgröße + Wetterlage als One-Hot
    lagen = ["Hochdruck", "Wechselhaft", "Regenfront"]
    basis_feature_namen = []
    for o in orte:
        for m in vorhandene_messgroessen:
            basis_feature_namen.append(f"{o}_{m}")
    for l in lagen:
        basis_feature_namen.append(f"lage_{l}")

    # 7) Jetzt样本 für样本 bauen
    X_zeilen, y_zeilen, meta = [], [], []

    # i = Index des "heute"-Tages in gemeinsame_tage
    for i, d in enumerate(gemeinsame_tage):

        # Brauchen mindestens FENSTER_TAGE Tage Historie
        if i < FENSTER_TAGE:
            continue

        # Das Eingabe-Fenster: die letzten FENSTER_TAGE Tage inkl. heute
        # Beispiel bei FENSTER_TAGE=7 und i=10:
        #   fenster = [Tag 4, 5, 6, 7, 8, 9, 10]
        fenster = gemeinsame_tage[i - FENSTER_TAGE + 1:i + 1]

        # 8) Alle Werte des Fensters zu EINEM flachen Vektor machen
        feat = []
        for fd in fenster:                    # für jeden Tag im Fenster
            for o in orte:                    # für jeden Ort
                zeile = zeilen_map[(fd, o)]
                for m in vorhandene_messgroessen:  # für jede Messgröße
                    feat.append(float(zeile.get(m, 0.0)))

            # Wetterlage als One-Hot (3 Werte: 1.0 an der richtigen Stelle)
            # Wir nehmen die Wetterlage vom ersten Ort an (sollte überall gleich sein)
            wl = zeilen_map[(fd, orte[0])].get("wetterlage", "Wechselhaft")
            for l in lagen:
                feat.append(1.0 if wl == l else 0.0)

        # 9) Zielwert bestimmen: ZIELGROESSE HORIZONT_TAGE nach dem Fenster
        ziel_index = i + HORIZONT_TAGE
        if ziel_index >= len(gemeinsame_tage):
            continue  # am Ende der Zeitreihe angekommen

        ziel_datum = gemeinsame_tage[ziel_index]

        # Ziel = Mittelwert der Zielgröße über alle Orte am Zieltag
        ziel_werte = [zeilen_map[(ziel_datum, o)].get(ZIELGROESSE) for o in orte]
        ziel_werte = [float(z) for z in ziel_werte if z is not None]
        if not ziel_werte:
            continue  # keine gültigen Zielwerte -> Sample überspringen
        ziel = float(np.mean(ziel_werte))

        # 10) Sample anhängen
        X_zeilen.append(feat)
        y_zeilen.append(ziel)
        meta.append({"eingabe_bis": d, "ziel_datum": ziel_datum})

    # 11) In numpy-Arrays umwandeln (sklearn will das so)
    X = np.array(X_zeilen, dtype=np.float32)
    y = np.array(y_zeilen, dtype=np.float32)

    # 12) Feature-Namen für das komplette Fenster erweitern
    #     (jeder Feature-Name bekommt ein "t-X_" Präfix für den Tag im Fenster)
    voll_feature_namen = []
    for t in range(FENSTER_TAGE):
        for fn in basis_feature_namen:
            voll_feature_namen.append(f"t-{FENSTER_TAGE - 1 - t}_{fn}")

    print(f"X: {X.shape}  y: {y.shape}  Features: {len(voll_feature_namen)}")
    return X, y, meta, voll_feature_namen, orte, vorhandene_messgroessen


# ==================================================
# TRAINING
# ==================================================

def trainiere():
    # sklearn-Importe hier drin, damit das Modul auch ohne sklearn
    # importierbar bleibt (z.B. für Tests)
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    # Seed setzen -> reproduzierbare Ergebnisse
    np.random.seed(ZUFALLS_SEED)

    # 1) Feature-Matrix bauen
    X, y, meta, feature_namen, orte, messgroessen = baue_feature_matrix()
    print(f"\nDatensätze: {X.shape[0]}  Features: {X.shape[1]}  Ziel: {ZIELGROESSE}")

    # 2) Zeitlicher Split (WICHTIG: nicht mischen!)
    #    Erste 80% = Training, letzte 20% = Test.
    #    So simuliert man "Vorhersage in die Zukunft".
    n = len(X)
    n_test = int(n * TEST_ANTEIL)
    n_train = n - n_test

    X_train, X_test = X[:n_train], X[n_train:]
    y_train, y_test = y[:n_train], y[n_train:]

    print(f"Train: {n_train}  Test: {n_test}")
    print(f"Train-Zeitraum: {meta[0]['eingabe_bis']} .. {meta[n_train-1]['ziel_datum']}")
    print(f"Test-Zeitraum:  {meta[n_train]['eingabe_bis']} .. {meta[-1]['ziel_datum']}")

    # 3) Skalierung: jede Feature-Spalte auf Mittelwert 0, Std 1 bringen.
    #    Wichtig, weil z.B. Luftdruck (~1000) und UV-Index (~0-10)
    #    völlig unterschiedliche Größenordnungen haben.
    #    WICHTIG: fit nur auf Trainingsdaten, sonst Data-Leakage!
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)   # nur transform, nicht fit!

    # 4) Modell definieren
    #    Gradient Boosting = viele kleine Entscheidungsbäume nacheinander,
    #    jeder korrigiert die Fehler des vorherigen.
    #    Robust bei tabellarischen Daten, kaum Tuning nötig.
    modell = GradientBoostingRegressor(
        n_estimators=300,     # Anzahl Bäume
        max_depth=4,          # Tiefe pro Baum (klein = weniger Overfitting)
        learning_rate=0.05,   # Lernrate (klein = vorsichtiger)
        random_state=ZUFALLS_SEED,
    )

    # 5) Training
    modell.fit(X_train_s, y_train)

    # 6) Vorhersagen auf Train und Test
    y_pred_train = modell.predict(X_train_s)
    y_pred_test = modell.predict(X_test_s)

    # 7) Evaluierung: MAE, RMSE, R²
    #    MAE  = mittlerer absoluter Fehler (in Einheiten der Zielgröße)
    #    RMSE = Wurzel des mittleren quadratischen Fehlers (bestraft große Fehler)
    #    R²   = wie viel Varianz erklärt das Modell? (1.0 = perfekt, 0 = nichts)
    print("\n=== Ergebnisse ===")
    for name, y_true, y_pred in [
        ("Train", y_train, y_pred_train),
        ("Test", y_test, y_pred_test),
    ]:
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        r2 = r2_score(y_true, y_pred)
        print(f"{name:>5}: MAE={mae:6.2f}  RMSE={rmse:6.2f}  R²={r2:6.3f}")

    # 8) Baseline: "morgen = heute" (Persistenz)
    #    Das ist der dümmste mögliche Prädiktor: nimm den letzten bekannten Wert.
    #    Wenn die KI nicht besser ist, hat sie nichts gelernt.
    #
    #    Index im flachen Feature-Vektor berechnen:
    #    Wir wollen den Wert der Zielgröße am LETZTEN Fenstertag, Ort 0.
    idx = (FENSTER_TAGE - 1) * len(orte) * len(messgroessen) \
          + orte.index(orte[0]) * len(messgroessen) \
          + messgroessen.index(ZIELGROESSE)
    baseline_test = X_test[:, idx]   # Spalte mit "Zielgröße heute"
    mae_b = mean_absolute_error(y_test, baseline_test)
    rmse_b = np.sqrt(mean_squared_error(y_test, baseline_test))
    print(f"\nBaseline (Persistenz): MAE={mae_b:6.2f}  RMSE={rmse_b:6.2f}")
    verb = (mae_b - mean_absolute_error(y_test, y_pred_test)) / mae_b * 100
    print(f"Verbesserung MAE: {verb:.1f}%")

    # 9) Feature-Wichtigkeit
    #    Zeigt, welche Eingaben das Modell am meisten nutzt.
    #    Nützlich, um zu prüfen, ob das Modell physikalisch Sinnvolles lernt.
    wichtigkeiten = sorted(
        zip(feature_namen, modell.feature_importances_),
        key=lambda x: -x[1],   # absteigend sortieren
    )
    print("\nTop-15 Features:")
    for fn, w in wichtigkeiten[:15]:
        print(f"  {w:.4f}  {fn}")

    # 10) Modell speichern (joblib = effizient für sklearn-Modelle)
    import joblib
    os.makedirs(MODELL_ORDNER, exist_ok=True)
    joblib.dump(modell, os.path.join(MODELL_ORDNER, "modell.joblib"))
    joblib.dump(scaler, os.path.join(MODELL_ORDNER, "scaler.joblib"))

    # Metadaten mitspeichern, damit man später weiß, wie das Modell
    # trainiert wurde (welche Orte, welche Features, welcher Horizont)
    with open(os.path.join(MODELL_ORDNER, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "zielgroesse": ZIELGROESSE,
            "horizont_tage": HORIZONT_TAGE,
            "fenster_tage": FENSTER_TAGE,
            "orte": orte,
            "messgroessen": messgroessen,
            "feature_namen": feature_namen,
            "test_anteil": TEST_ANTEIL,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nModell gespeichert in: {MODELL_ORDNER}")

    # 11) Ein paar Beispiel-Vorhersagen aus dem Testset zeigen
    print("\nBeispiel-Vorhersagen (Test):")
    for i in range(min(5, len(y_test))):
        print(f"  {meta[n_train + i]['ziel_datum']}: "
              f"wahr={y_test[i]:6.2f}  vorhergesagt={y_pred_test[i]:6.2f}")


# ==================================================
# EINSTIEGSPUNKT
# ==================================================
# Wird nur ausgeführt, wenn man das Skript direkt startet
# (nicht, wenn es von einem anderen Skript importiert wird)
if __name__ == "__main__":
    trainiere()