import csv
import json
import re
import os

# --- KONFIGURATION ---
INPUT_CSV = "laptops_rohdaten.csv"       # Deine heruntergeladene CSV-Datei (z. B. von Kaggle)
EXISTING_JSON = "modelle.json"          # Deine bestehende Datenbank (wird NUR erweitert!)
OUTPUT_JSON = "modelle_erweitert.json"  # Die fertige, valide Ausgabedatei

# Mapping der CSV-Spaltennamen (anpassen, falls deine CSV anders heißt, z. B. "Brand", "Model", "RAM")
COL_BRAND = "Company"      # Hersteller (z. B. Lenovo, ASUS, HP)
COL_MODEL = "Product"      # Modellbezeichnung (z. B. IdeaPad 3 15ALC6)
COL_CPU = "Cpu"            # Prozessor (z. B. AMD Ryzen 7 5800H, Intel Core i7-13700H)
COL_RAM = "Ram"            # Verbauter RAM (z. B. "16GB" oder "8")
COL_GPU = "Gpu"            # Verbaute GPU (z. B. "Nvidia GeForce RTX 4060")


def clean_text(text):
    """Entfernt Zeilenumbrüche und Steuerzeichen, damit JSON niemals bricht."""
    if not text:
        return ""
    return re.sub(r'[\r\n\t]+', ' ', str(text)).strip()


def generate_slug(brand, title):
    """Erzeugt eine saubere, eindeutige ID für das JSON."""
    raw = f"{brand}-{title}".lower()
    slug = re.sub(r'[^a-z0-9]+', '-', raw).strip('-')
    return slug[:60]


def parse_ram_gb(ram_str):
    """Extrahiert die Zahl aus Strings wie '16GB' oder '8 GB'."""
    match = re.search(r'(\d+)', str(ram_str))
    return int(match.group(1)) if match else 8


def determine_upgrade_rules(brand, model, cpu, ram_gb):
    """
    Regelwerk zur automatischen Bestimmung von RAM-Typ, Slots, Max-RAM und Hinweisen.
    """
    b_low = brand.lower()
    m_low = model.lower()
    c_low = cpu.lower()

    # 1. Sonderfall: Apple MacBooks (immer verlötet)
    if "apple" in b_low or "macbook" in m_low:
        return {
            "maxRamGB": ram_gb,
            "slotsInfo": "0 Steckplätze (Unified Memory fest im Chip integriert)",
            "ramTyp": "Fest verlöteter Unified Memory",
            "hinweisStandard": "Achtung: Bei Apple MacBooks ist der Arbeitsspeicher fest verlötet und nachträglich nicht aufrüstbar.",
            "hinweisUpgrade": "Ein nachträgliches RAM-Upgrade ist bei diesem Modell technisch ausgeschlossen."
        }

    # 2. Sonderfall: Ultrabooks mit typischerweise verlötetem LPDDR-Speicher
    soldered_keywords = ["zenbook", "xps 13", "yoga slim", "ideapad slim", "swift", "gram", "surface", "envy x360 13", "spectre"]
    if any(kw in m_low for kw in soldered_keywords):
        return {
            "maxRamGB": ram_gb,
            "slotsInfo": "0 Steckplätze (LPDDR-Speicher fest auf dem Mainboard verlötet)",
            "ramTyp": "LPDDR4X / LPDDR5 (Fest verlötet)",
            "hinweisStandard": f"Dieses flache Ultrabook besitzt {ram_gb} GB fest verlöteten Arbeitsspeicher.",
            "hinweisUpgrade": "Aufgrund der kompakten Bauweise sind keine freien Steckplätze vorhanden."
        }

    # 3. CPU-Generation erkennen -> DDR5 vs. DDR4 bestimmen
    is_ddr5 = False
    # Intel 12., 13., 14. Gen oder Core Ultra
    if re.search(r'i[3579]-1[234]\d{3}|core ultra', c_low):
        is_ddr5 = True
    # AMD Ryzen 6000, 7000, 8000, 9000 oder Ryzen AI
    if re.search(r'ryzen [3579] [6789]\d{3}|ryzen ai', c_low):
        is_ddr5 = True

    ram_typ = "DDR5 SODIMM 5600MHz" if is_ddr5 else "DDR4 SODIMM 3200MHz"

    # 4. Gaming & Workstation Notebooks erkennen -> 2 Slots, bis zu 64 GB
    gaming_keywords = ["legion", "rog", "strix", "tuf", "nitro", "predator", "omen", "victus", "katana", "raider", "vector", "blade", "aorus", "xmg", "alienware", "precision", "zbook", "thinkpad p", "thinkpad t"]
    if any(kw in m_low for kw in gaming_keywords):
        max_ram = 64
        slots_info = "2 SODIMM Steckplätze vorhanden (voll aufrüstbar)"
        hinweis_std = f"Ab Werk mit {ram_gb} GB ausgestattet. Ideal für Gaming und anspruchsvolle Anwendungen."
        hinweis_upg = f"Kann problemlos auf 32 GB oder {max_ram} GB ({ram_typ}) im Dual-Channel aufgerüstet werden."
    else:
        # Klassische Allround- & Office-Notebooks (oft 1 Slot frei oder 2 Slots bis 32 GB)
        max_ram = 32
        slots_info = "1–2 SODIMM Steckplätze (aufrüstbar)"
        hinweis_std = f"Mit {ram_gb} GB RAM gut geeignet für Office, Surfen und Home-Office."
        hinweis_upg = f"Für flüssiges Multitasking empfiehlt sich die Erweiterung auf 16 GB oder {max_ram} GB ({ram_typ})."

    return {
        "maxRamGB": max_ram,
        "slotsInfo": slots_info,
        "ramTyp": ram_typ,
        "hinweisStandard": hinweis_std,
        "hinweisUpgrade": hinweis_upg
    }


def main():
    # Bestehende JSON-Datenbank laden (falls vorhanden), damit nichts verloren geht
    datenbank = []
    vorhandene_ids = set()

    if os.path.exists(EXISTING_JSON):
        with open(EXISTING_JSON, "r", encoding="utf-8") as f:
            datenbank = json.load(f)
            for eintrag in datenbank:
                vorhandene_ids.add(eintrag.get("id"))
        print(f"Bestehende Datenbank geladen: {len(datenbank)} Einträge vorhanden.")

    if not os.path.exists(INPUT_CSV):
        print(f"Hinweis: '{INPUT_CSV}' nicht gefunden. Lege eine Beispiel-CSV an...")
        with open(INPUT_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[COL_BRAND, COL_MODEL, COL_CPU, COL_RAM, COL_GPU])
            writer.writeheader()
            writer.writerow({COL_BRAND: "Lenovo", COL_MODEL: "Legion Pro 5 16IRX8", COL_CPU: "Intel Core i7-13700HX", COL_RAM: "16GB", COL_GPU: "NVIDIA GeForce RTX 4060"})
            writer.writerow({COL_BRAND: "HP", COL_MODEL: "Pavilion 15-eg2055ng", COL_CPU: "Intel Core i5-1235U", COL_RAM: "8GB", COL_GPU: "Intel Iris Xe"})

    neu_hinzugefuegt = 0

    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        # Erkennt automatisch, ob die CSV mit Komma oder Semikolon getrennt ist
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        reader = csv.DictReader(f, dialect=dialect)

        for row in reader:
            brand = clean_text(row.get(COL_BRAND, ""))
            model = clean_text(row.get(COL_MODEL, ""))
            cpu = clean_text(row.get(COL_CPU, ""))
            gpu = clean_text(row.get(COL_GPU, ""))
            ram_gb = parse_ram_gb(row.get(COL_RAM, "8"))

            if not brand or not model:
                continue

            eintrag_id = generate_slug(brand, model)

            # Duplikate überspringen, bestehende Einträge niemals löschen
            if eintrag_id in vorhandene_ids:
                continue

            regeln = determine_upgrade_rules(brand, model, cpu, ram_gb)

            suchbegriffe = clean_text(f"{brand} {model} {cpu} {gpu}").lower()

            neuer_eintrag = {
                "id": eintrag_id,
                "hersteller": brand,
                "titel": model,
                "suchbegriffe": suchbegriffe,
                "kategorie": "Notebook",
                "standardRamGB": ram_gb,
                "maxRamGB": regeln["maxRamGB"],
                "slotsInfo": regeln["slotsInfo"],
                "ramTyp": regeln["ramTyp"],
                "varianten": [
                    {
                        "label": f"Werkskonfiguration ({ram_gb} GB RAM / {cpu})",
                        "standardRamGB": ram_gb
                    }
                ],
                "hinweisStandard": regeln["hinweisStandard"],
                "hinweisUpgrade": regeln["hinweisUpgrade"]
            }

            datenbank.append(neuer_eintrag)
            vorhandene_ids.add(eintrag_id)
            neu_hinzugefuegt += 1

    # Sauberes, valides JSON ohne unzulässige Steuerzeichen speichern
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(datenbank, f, ensure_ascii=False, indent=2)

    print(f"Fertig! {neu_hinzugefuegt} neue Modelle hinzugefügt. Gesamtbestand in '{OUTPUT_JSON}': {len(datenbank)} Modelle.")


if __name__ == "__main__":
    main()
