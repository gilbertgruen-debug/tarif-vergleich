import csv
import json
import re
import os

# --- KONFIGURATION ---
INPUT_CSV = "laptops_rohdaten.csv"       # Deine heruntergeladene CSV-Datei
EXISTING_RAM_JSON = "modelle.json"      # Bestehende RAM-Datenbank (wird NUR erweitert!)
OUTPUT_RAM_JSON = "modelle_erweitert.json"

EXISTING_GPU_JSON = "gpus.json"         # Bestehende GPU-Datenbank (wird NUR erweitert!)
OUTPUT_GPU_JSON = "gpus_erweitert.json"

# Mapping der CSV-Spaltennamen
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


def determine_ram_rules(brand, model, cpu, ram_gb):
    """Regelwerk für RAM-Typ, Slots, Max-RAM und Hinweise."""
    b_low = brand.lower()
    m_low = model.lower()
    c_low = cpu.lower()

    if "apple" in b_low or "macbook" in m_low:
        return {
            "maxRamGB": ram_gb,
            "slotsInfo": "0 Steckplätze (Unified Memory fest im Chip integriert)",
            "ramTyp": "Fest verlöteter Unified Memory",
            "hinweisStandard": "Achtung: Bei Apple MacBooks ist der Arbeitsspeicher fest verlötet und nachträglich nicht aufrüstbar.",
            "hinweisUpgrade": "Ein nachträgliches RAM-Upgrade ist bei diesem Modell technisch ausgeschlossen."
        }

    soldered_keywords = ["zenbook", "xps 13", "yoga slim", "ideapad slim", "swift", "gram", "surface", "envy x360 13", "spectre"]
    if any(kw in m_low for kw in soldered_keywords):
        return {
            "maxRamGB": ram_gb,
            "slotsInfo": "0 Steckplätze (LPDDR-Speicher fest auf dem Mainboard verlötet)",
            "ramTyp": "LPDDR4X / LPDDR5 (Fest verlötet)",
            "hinweisStandard": f"Dieses flache Ultrabook besitzt {ram_gb} GB fest verlöteten Arbeitsspeicher.",
            "hinweisUpgrade": "Aufgrund der kompakten Bauweise sind keine freien Steckplätze vorhanden."
        }

    is_ddr5 = bool(
        re.search(r'i[3579]-1[234]\d{3}|core ultra', c_low) or
        re.search(r'ryzen [3579] [6789]\d{3}|ryzen ai', c_low)
    )
    ram_typ = "DDR5 SODIMM 5600MHz" if is_ddr5 else "DDR4 SODIMM 3200MHz"

    gaming_keywords = [
        "legion", "rog", "strix", "tuf", "nitro", "predator", "omen", "victus",
        "katana", "raider", "vector", "blade", "aorus", "xmg", "alienware",
        "precision", "zbook", "thinkpad p", "thinkpad t"
    ]
    if any(kw in m_low for kw in gaming_keywords):
        max_ram = 64
        slots_info = "2 SODIMM Steckplätze vorhanden (voll aufrüstbar)"
        hinweis_std = f"Ab Werk mit {ram_gb} GB ausgestattet. Ideal für Gaming und anspruchsvolle Anwendungen."
        hinweis_upg = f"Kann problemlos auf 32 GB oder {max_ram} GB ({ram_typ}) im Dual-Channel aufgerüstet werden."
    else:
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


def determine_gpu_rules(brand, gpu_str):
    """Regelwerk für VRAM, Leistungsklasse und Upgrade-Hinweise bei Notebooks."""
    g_low = gpu_str.lower()
    b_low = brand.lower()

    if "apple" in b_low or "m1" in g_low or "m2" in g_low or "m3" in g_low or "m4" in g_low:
        return {
            "vramGB": 16,
            "leistungsklasse": "Professioneller Grafikprozessor",
            "hinweisStandard": "Grafikeinheit ist direkt im Apple Silicon Chip integriert.",
            "hinweisUpgrade": "Achtung: Ein nachträgliches Grafik- oder Speicherupgrade ist bei Apple MacBooks unmöglich."
        }

    if any(x in g_low for x in ["4090", "4080", "3080", "7900"]):
        vram = 16 if "4090" in g_low or "7900" in g_low else 12
        klasse = "High-End Gaming"
        std_text = "Maximale Grafikleistung für WQHD und 4K Gaming sowie anspruchsvolles Rendering."
    elif any(x in g_low for x in ["4070", "3070", "6800", "7700"]):
        vram = 8
        klasse = "Gehobene Mittelklasse Gaming"
        std_text = "Starke Grafikleistung für flüssiges WQHD (1440p) Gaming."
    elif any(x in g_low for x in ["4060", "3060", "6700", "7600"]):
        vram = 8
        klasse = "Mittelklasse Gaming"
        std_text = "Solide Gaming-Performance für Full-HD und aktuelle Titel."
    elif any(x in g_low for x in ["4050", "3050", "2050", "1660", "1650", "6600", "6500"]):
        vram = 6 if any(x in g_low for x in ["4050", "1660", "6600"]) else 4
        klasse = "Einsteiger Gaming"
        std_text = "Gute Basis für Full-HD Gaming und eSports-Titel."
    else:
        vram = 4
        klasse = "Office & Multimedia (Integrierte Grafik)"
        std_text = "Energieeffiziente integrierte Grafikeinheit für Büroarbeiten, Streaming und leichtes Gaming."

    return {
        "vramGB": vram,
        "leistungsklasse": klasse,
        "hinweisStandard": std_text,
        "hinweisUpgrade": "Laptop-Grafikkarten sind fest auf dem Mainboard verlötet und lassen sich nachträglich nicht aufrüsten. Eine Leistungssteigerung ist nur über eine externe eGPU (via Thunderbolt/USB4) oder einen Neukauf möglich."
    }


def load_existing_json(filepath):
    """Lädt eine bestehende JSON-Datei und gibt die Liste sowie ein Set aller IDs zurück."""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            ids = {item.get("id") for item in data if item.get("id")}
            return data, ids
    return [], set()


def main():
    ram_db, ram_ids = load_existing_json(EXISTING_RAM_JSON)
    gpu_db, gpu_ids = load_existing_json(EXISTING_GPU_JSON)

    print(f"Geladen: {len(ram_db)} RAM-Modelle | {len(gpu_db)} GPU-Modelle")

    if not os.path.exists(INPUT_CSV):
        print(f"Hinweis: '{INPUT_CSV}' nicht gefunden. Lege eine Beispiel-CSV an...")
        with open(INPUT_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[COL_BRAND, COL_MODEL, COL_CPU, COL_RAM, COL_GPU])
            writer.writeheader()
            writer.writerow({COL_BRAND: "Lenovo", COL_MODEL: "Legion Pro 5 16IRX8", COL_CPU: "Intel Core i7-13700HX", COL_RAM: "16GB", COL_GPU: "NVIDIA GeForce RTX 4060"})
            writer.writerow({COL_BRAND: "HP", COL_MODEL: "Pavilion 15-eg2055ng", COL_CPU: "Intel Core i5-1235U", COL_RAM: "8GB", COL_GPU: "Intel Iris Xe"})

    neu_ram = 0
    neu_gpu = 0

    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        reader = csv.DictReader(f, dialect=dialect)

        for row in reader:
            brand = clean_text(row.get(COL_BRAND, ""))
            model = clean_text(row.get(COL_MODEL, ""))
            cpu = clean_text(row.get(COL_CPU, ""))
            gpu = clean_text(row.get(COL_GPU, "")) or "Integrierte Grafik"
            ram_gb = parse_ram_gb(row.get(COL_RAM, "8"))

            if not brand or not model:
                continue

            base_slug = generate_slug(brand, model)
            suchbegriffe = clean_text(f"{brand} {model} {cpu} {gpu}").lower()

            # 1. RAM-Datenbank erweitern
            if base_slug not in ram_ids:
                ram_rules = determine_ram_rules(brand, model, cpu, ram_gb)
                ram_db.append({
                    "id": base_slug,
                    "hersteller": brand,
                    "titel": model,
                    "suchbegriffe": suchbegriffe,
                    "kategorie": "Notebook",
                    "standardRamGB": ram_gb,
                    "maxRamGB": ram_rules["maxRamGB"],
                    "slotsInfo": ram_rules["slotsInfo"],
                    "ramTyp": ram_rules["ramTyp"],
                    "varianten": [
                        {
                            "label": f"Werkskonfiguration ({ram_gb} GB RAM / {cpu})",
                            "standardRamGB": ram_gb
                        }
                    ],
                    "hinweisStandard": ram_rules["hinweisStandard"],
                    "hinweisUpgrade": ram_rules["hinweisUpgrade"]
                })
                ram_ids.add(base_slug)
                neu_ram += 1

            # 2. GPU-Datenbank erweitern
            gpu_slug = f"gpu-{base_slug}"[:60]
            if gpu_slug not in gpu_ids:
                gpu_rules = determine_gpu_rules(brand, gpu)
                gpu_db.append({
                    "id": gpu_slug,
                    "hersteller": brand,
                    "titel": model,
                    "suchbegriffe": suchbegriffe,
                    "kategorie": "Notebook",
                    "verbautGpu": gpu,
                    "vramGB": gpu_rules["vramGB"],
                    "leistungsklasse": gpu_rules["leistungsklasse"],
                    "varianten": [
                        {
                            "label": f"Werkskonfiguration ({gpu})",
                            "verbautGpu": gpu
                        }
                    ],
                    "hinweisStandard": gpu_rules["hinweisStandard"],
                    "hinweisUpgrade": gpu_rules["hinweisUpgrade"]
                })
                gpu_ids.add(gpu_slug)
                neu_gpu += 1

    with open(OUTPUT_RAM_JSON, "w", encoding="utf-8") as f:
        json.dump(ram_db, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_GPU_JSON, "w", encoding="utf-8") as f:
        json.dump(gpu_db, f, ensure_ascii=False, indent=2)

    print(f"RAM-DB fertig: +{neu_ram} neu -> Gesamt {len(ram_db)} Einträge in '{OUTPUT_RAM_JSON}'")
    print(f"GPU-DB fertig: +{neu_gpu} neu -> Gesamt {len(gpu_db)} Einträge in '{OUTPUT_GPU_JSON}'")


if __name__ == "__main__":
    main()
