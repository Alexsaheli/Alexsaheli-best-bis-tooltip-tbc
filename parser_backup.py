import re
from curl_cffi import requests
from bs4 import BeautifulSoup

VERSION = "1.8"

def parse_page(url, spec, phase):
    print(f"[Wowhead] Парсим: {spec} — {phase}...")
    items = {}
    try:
        response = requests.get(url, impersonate="chrome")
        if response.status_code != 200: 
            print(f"  (!) Ошибка доступа: {response.status_code}")
            return items
            
        soup = BeautifulSoup(response.text, "html.parser")
        # Ищем основной блок контента гайда
        container = soup.find("div", {"class": "guide-content"}) or soup
        tables = container.find_all("table")

        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2: continue
                
                # Ищем ссылки именно на предметы
                links = cells[1].find_all("a", {"data-type": "item"})
                for link in links:
                    href = link.get("href", "")
                    match = re.search(r"item=(\d+)", href)
                    if match:
                        item_id = int(match.group(1))
                        items[item_id] = "Absolute BiS"
    except Exception as e:
        print(f"  (!) Ошибка парсинга {spec} {phase}: {e}")
    return items

def main():
    # Твои классы и спеки
    urls = {
        "priest": {
            "shadow_priest": {
                "pre": "https://www.wowhead.com/tbc/guide/classes/priest/shadow/dps-bis-gear-pve-pre-raid",
                "p1": "https://www.wowhead.com/tbc/guide/shadow-priest-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
                "p2": "https://www.wowhead.com/tbc/guide/classes/priest/shadow/dps-bis-gear-pve-phase-2"
            },
            "holy_priest": {
                "pre": "https://www.wowhead.com/tbc/guide/classes/priest/healer-bis-gear-pve-pre-raid",
                "p1": "https://www.wowhead.com/tbc/guide/priest-healer-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
                "p2": "https://www.wowhead.com/tbc/guide/classes/priest/healer-bis-gear-pve-phase-2"
            }
        }
    }
    
    master_db = {}
    all_item_ids = set()

    for char_class, specs in urls.items():
        master_db[char_class] = {}
        for spec, phases in specs.items():
            master_db[char_class][spec] = {}
            for phase, url in phases.items():
                data = parse_page(url, spec, phase)
                master_db[char_class][spec][phase] = data
                all_item_ids.update(data.keys())

    # Запись в файл
    with open("bisdata.lua", "w", encoding="utf-8") as f:
        f.write("BestBisListData = {\n")
        for item_id in sorted(all_item_ids):
            f.write(f"    [{item_id}] = {{\n")
            for char_class, specs in master_db.items():
                for spec, phases in specs.items():
                    phases_data = {p: phases[p].get(item_id) for p in ["pre", "p1", "p2"] if phases[p].get(item_id)}
                    if phases_data:
                        f.write(f"        [\"{spec}\"] = {{\n")
                        for p, status in phases_data.items():
                            f.write(f"            [\"{p}\"] = \"{status}\",\n")
                        f.write("        },\n")
            f.write("    },\n")
        f.write("}\n")
    print(f"\nГотово! Файл bisdata.lua создан.")

if __name__ == "__main__":
    main()