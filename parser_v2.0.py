import re
import json
import os
from curl_cffi import requests
from bs4 import BeautifulSoup

# Всегда пишем bisdata.lua рядом со скриптом, независимо от рабочей директории
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

VERSION = "2.7"

# ---------------------------------------------------------------------------
# Извлечение BBCode из новых страниц Wowhead (формат /classes/...)
# Контент лежит в <script type="application/json" id="data.{guid}">
# ---------------------------------------------------------------------------
def extract_bbcode(html_text):
    """
    Два формата Wowhead:
    1. Новый: данные в <script type="application/json" id="data.{guid}">.
       Guid берётся из WH.markup.printHtml(WH.getPageData("{guid}"), "guide-body", ...).
    2. Инлайн: BBCode строка передаётся напрямую:
       WH.markup.printHtml("...", "guide-body")
       Используется на pre-raid и p1 страницах warrior.
    Возвращает строку BBCode или None.
    """
    # --- Формат 1: WH.getPageData ---
    guid_match = re.search(
        r'WH\.markup\.printHtml\(\s*WH\.getPageData\("([^"]+)"\)\s*,\s*"guide-body"',
        html_text
    )
    if guid_match:
        guid = guid_match.group(1)
        tag_pattern = re.compile(
            r'<script[^>]+id="data\.' + re.escape(guid) + r'"[^>]*>(.*?)</script>',
            re.DOTALL
        )
        tag_match = tag_pattern.search(html_text)
        if tag_match:
            raw = tag_match.group(1).strip()
            try:
                decoded = json.loads(raw)
                print(f"      [DEBUG] json.loads type={type(decoded).__name__}, preview={repr(decoded)[:120]}")
                if isinstance(decoded, str):
                    return decoded
                else:
                    # dict или list — не BBCode строка, пробуем как есть
                    return str(decoded)
            except Exception:
                if raw.startswith('"') and raw.endswith('"'):
                    raw = raw[1:-1]
                decoded = raw.replace('\\"', '"').replace('\\n', '\n').replace('\\r', '').replace('\\\\', '\\')
                print(f"      [DEBUG] raw decode, preview={repr(decoded)[:120]}")
                return decoded
        # guid найден но тег не найден — не пробуем формат 2, это не inline страница
        return None

    # --- Формат 2: инлайн BBCode строка ---
    # WH.markup.printHtml("...", "guide-body") — строка передаётся напрямую
    # Ищем начало строки, затем берём всё до закрывающего ", "guide-body"
    inline_match = re.search(
        r'WH\.markup\.printHtml\(\s*"(.*?)",\s*"guide-body"',
        html_text,
        re.DOTALL
    )
    if inline_match:
        raw = inline_match.group(1)
        return raw.replace('\\"', '"').replace('\\n', '\n').replace('\\r', '').replace('\\\\', '\\').replace("\\'", "'")

    return None


# ---------------------------------------------------------------------------
# Парсинг BBCode (новые страницы /classes/...)
# ---------------------------------------------------------------------------
OPTIONAL_KEYWORDS = [
    "optional", "option", "sub-bis", "recommended", "honorable mention",
    "honorable mentions", "other option", "other recommendation", "easy to obtain",
    "further option",
]

TOGGLER_KEYWORDS = [
    "further options", "other recommendations", "other options",
    "honorable mentions", "additional options",
]

SUFFIX_KEYWORDS = [
    "hit alternative", "hit cap", "need hit", "if you need hit",
    "threat alternative", "best threat",
    "horde only", "alliance only",
    "jewelcrafting", "jc only", "if you do jewelcrafting",
    "against demon", "against demons",
    "scryers only", "scryers",
    "slow alternative", "fast alternative",
    "crafted alternative", "mitigation alternative",
    "orc only", "orc",
    "with sword spec", "sword spec",
]


def extract_suffix(rank_text):
    t = rank_text.strip().lower()
    for kw in SUFFIX_KEYWORDS:
        if kw in t:
            return kw.title()
    return None


def is_optional_rank(rank_text):
    t = rank_text.strip().lower()
    return any(kw in t for kw in OPTIONAL_KEYWORDS)


def extract_item_ids_bbcode(cell_text):
    return [int(m) for m in re.findall(r'\[item=(\d+)', cell_text, re.IGNORECASE)]


def detect_icon_prefix(cell_text):
    """
    Определяет иконку Shadow/Fire Destro из BBCode ячейки.
    Возвращает 'shadow', 'fire' или None.
    """
    if re.search(r'\[icon\s+name=spell_shadow_shadowbolt\]', cell_text, re.IGNORECASE):
        return 'shadow'
    if re.search(r'\[icon\s+name=spell_fire_burnout\]', cell_text, re.IGNORECASE):
        return 'fire'
    return None


def strip_icon_tags(text):
    """Убирает [icon ...][/icon] теги из текста."""
    return re.sub(r'\[icon[^\]]*\].*?\[/icon\]', '', text, flags=re.DOTALL | re.IGNORECASE).strip()


# Счётчики для Best Hit (сбрасываются на каждый слот)
_best_hit_slot_counter = {}


def parse_bbcode_table_rows(table_bbcode):
    rows = []
    for tr_match in re.finditer(r'\[tr\](.*?)\[/tr\]', table_bbcode, re.DOTALL | re.IGNORECASE):
        tr_content = tr_match.group(1)
        cells = []
        for td_match in re.finditer(r'\[td(?:[^\]]*)?\](.*?)\[/td\]', tr_content, re.DOTALL | re.IGNORECASE):
            cells.append(td_match.group(1).strip())
        if cells:
            rows.append(cells)
    return rows


def process_bbcode_table_rows(rows, in_toggler, slot_first_item_done, debug_spec=None, slot_name=None):
    """
    Логика статусов:
    - in_toggler: всегда Sub-BiS Further Options
    - Первая строка с предметом в слоте: Absolute BiS (+ приписка для демонов/JC)
    - Ранг "Option/Optional/..." до конца таблицы: Sub-BiS (Optional) + приписка
    - Всё остательное между первым и Optional: Close to BiS + приписка

    Новые особые случаи:
    - [icon name=spell_shadow_shadowbolt] → суффикс " - Shadow Destro"
    - [icon name=spell_fire_burnout] → суффикс " - Fire Destro"
    - rank содержит "set" → "Absolute BiS (When Tier Bonus)"
    - rank "unrealistic" → "Absolute BiS"
    - rank "realistic" → "Absolute BiS (Realistic)"
    - rank "best hit" #1 → "Absolute BiS (Hit)", #2 → "Close to BiS (Hit)"
    - rank "best over hit" → "Absolute BiS (When Hit Capped)"
    - rank содержит "pre pull trinket swap" → позиционный ранг + "(Pre Pull Trinket Swap)"

    Warrior weapon rank types (передаётся через slot_name):
    - rank "best main hand" → Absolute BiS - Main Hand
    - rank "best off hand" → Absolute BiS - Off Hand
    - rank "off-hand alternative" / "offhand alternative" → Sub-BiS - Off-Hand Alternative
    - rank "orc off-hand" → позиционный ранг + " - Orc Off-Hand" (в toggler → Sub-BiS Further Options - Orc Off-Hand)
    - rank "human off-hand" → позиционный ранг + " - Human Off-Hand" (в toggler → Sub-BiS Further Options - Human Off-Hand)
    - slot_name содержит "two-hand" → добавляем " - 2-Hander" к рангу
    - slot_name содержит "two-hand" И "sword" → добавляем также " - Sword Specced"
    """
    items = {}
    is_optional_section = False
    best_hit_count = 0  # счётчик "best hit" в этой таблице
    item_row_index = 0  # номер строки с предметом (для проверки позиции 1-4)


    for cells in rows:
        if len(cells) < 2:
            continue

        all_item_ids = []
        rank_text = ""
        item_cell_idx = -1
        icon_prefix = None  # 'shadow', 'fire' или None

        for i, cell in enumerate(cells):
            ids = extract_item_ids_bbcode(cell)
            if ids:
                all_item_ids.extend(ids)
                if item_cell_idx == -1:
                    item_cell_idx = i

        if not all_item_ids:
            continue

        item_row_index += 1  # считаем только строки с предметами

        # Извлекаем текст ранга из не-предметной ячейки + определяем иконку
        for i, cell in enumerate(cells):
            if i == item_cell_idx:
                continue
            if not extract_item_ids_bbcode(cell):
                # Определяем иконку из этой ячейки
                cell_icon = detect_icon_prefix(cell)
                if cell_icon:
                    icon_prefix = cell_icon
                candidate = strip_icon_tags(cell).strip()
                # Убираем BBCode теги кроме [item=...]
                candidate = re.sub(r'\[(?!item)[^\]]*\]', '', candidate).strip()
                if candidate:
                    rank_text = candidate
                    break

        # Также проверяем иконку в ячейке с предметами
        if item_cell_idx >= 0 and icon_prefix is None:
            cell_icon = detect_icon_prefix(cells[item_cell_idx])
            if cell_icon:
                icon_prefix = cell_icon

        suffix = extract_suffix(rank_text)
        rank_lower = rank_text.lower().strip()

        # --- Особые случаи по тексту ранга ---
        is_pre_pull = "pre pull trinket swap" in rank_lower or "pre-pull trinket swap" in rank_lower
        # Tier Set Bonus: слово "set" в ранге И предмет на позиции 1-4 в таблице
        is_tier_set = bool(re.search(r'\bset\b', rank_lower)) and item_row_index <= 4
        is_unrealistic = rank_lower == "unrealistic" or rank_lower == "best (unrealistic)"
        is_realistic = rank_lower == "realistic" or rank_lower == "best (realistic)"
        is_best_over_hit = "best over hit" in rank_lower or "over hit" in rank_lower
        is_best_hit = re.search(r'\bbest\s+hit\b', rank_lower) is not None and not is_best_over_hit

        # --- Warrior weapon rank types ---
        is_best_main_hand = rank_lower == "best main hand"
        is_best_off_hand = rank_lower == "best off hand"
        is_off_hand_alt = "off-hand alternative" in rank_lower or "offhand alternative" in rank_lower
        is_orc_off_hand = rank_lower == "orc off-hand"
        is_human_off_hand = rank_lower == "human off-hand"

        # Toggler toggler-rank overrides: в toggler Orc/Human off-hand → Sub-BiS Further Options + суффикс
        if in_toggler and is_orc_off_hand:
            status = "Sub-BiS Further Options - Orc Off-Hand"
        elif in_toggler and is_human_off_hand:
            status = "Sub-BiS Further Options - Human Off-Hand"
        elif in_toggler:
            status = "Sub-BiS Further Options"
        elif is_best_main_hand:
            status = "Absolute BiS - Main Hand"
            if not slot_first_item_done:
                slot_first_item_done = True
        elif is_best_off_hand:
            status = "Absolute BiS - Off Hand"
            if not slot_first_item_done:
                slot_first_item_done = True
        elif is_off_hand_alt:
            status = "Sub-BiS (Off-Hand Alternative)"
        elif is_optional_section or is_optional_rank(rank_text):
            is_optional_section = True
            status = "Sub-BiS (Optional)" + (" - " + suffix if suffix else "")
        elif is_best_over_hit:
            # "Best Over Hit" → Absolute BiS (When Hit Capped)
            status = "Absolute BiS (When Hit Capped)"
            if not slot_first_item_done:
                slot_first_item_done = True
        elif is_best_hit:
            # Первое "Best Hit" → Absolute BiS (Hit), второе → Close to BiS (Hit)
            best_hit_count += 1
            if best_hit_count == 1:
                status = "Absolute BiS (Hit)"
            else:
                status = "Close to BiS (Hit)"
            if not slot_first_item_done:
                slot_first_item_done = True
        elif is_unrealistic:
            status = "Absolute BiS"
            if not slot_first_item_done:
                slot_first_item_done = True
        elif is_realistic:
            status = "Absolute BiS (Realistic)"
            if not slot_first_item_done:
                slot_first_item_done = True
        elif is_tier_set:
            status = "Absolute BiS (When Tier Bonus)"
            if not slot_first_item_done:
                slot_first_item_done = True
        elif not slot_first_item_done:
            # Первый предмет в слоте — Absolute BiS
            if "demon" in rank_lower or "against demon" in rank_lower:
                status = "Absolute BiS (Against Demons)"
            elif "jewelcrafting" in rank_lower or "jc only" in rank_lower:
                status = "Absolute BiS (Jewelcrafting)"
            else:
                status = "Absolute BiS"
            slot_first_item_done = True
        else:
            # Всё что после первого и до Optional — Close to BiS
            status = "Close to BiS" + (" - " + suffix if suffix else "")

        # Pre Pull Trinket Swap — добавляем к позиционному рангу
        if is_pre_pull:
            # Убираем суффикс если есть, добавляем (Pre Pull Trinket Swap)
            base = status.split(" - ")[0] if " - " in status else status
            status = base + " (Pre Pull Trinket Swap)"

        # Shadow/Fire Destro суффикс — добавляем через тире
        if icon_prefix == 'shadow':
            status = status + " - Shadow Destro"
        elif icon_prefix == 'fire':
            status = status + " - Fire Destro"

        if debug_spec:
            print(f"      [DEBUG {debug_spec}] row={item_row_index} rank={repr(rank_text)} icon={icon_prefix} -> {status} | ids={all_item_ids[:2]}")

        for item_id in all_item_ids:
            if item_id not in items:
                items[item_id] = status

    return items, slot_first_item_done


def parse_bbcode(bbcode, spec_key=None):
    result = {}
    debug = False  # включить для отладки конкретного спека

    # Ищем h2 и h3 как разделители слотов (разные страницы используют разные уровни)
    heading_pattern = re.compile(r'\[h[23][^\]]*\](.*?)\[/h[23]\]', re.DOTALL | re.IGNORECASE)
    heading_positions = list(heading_pattern.finditer(bbcode))

    if debug:
        print(f"    [DEBUG] Заголовков слотов найдено: {len(heading_positions)}")
        for m in heading_positions[:8]:
            slot_text = re.sub(r'\[.*?\]', '', m.group(1)).strip()
            print(f"      -> {slot_text!r}")
        table_count = len(re.findall(r'\[table\]', bbcode, re.IGNORECASE))
        print(f"    [DEBUG] Таблиц в BBCode: {table_count}")

    if not heading_positions:
        slot_sections = [("unknown", bbcode)]
    else:
        slot_sections = []
        for i, m in enumerate(heading_positions):
            slot_name = re.sub(r'\[.*?\]', '', m.group(1)).strip()
            start = m.end()
            end = heading_positions[i + 1].start() if i + 1 < len(heading_positions) else len(bbcode)
            slot_sections.append((slot_name, bbcode[start:end]))

    for slot_name, slot_content in slot_sections:
        slot_first_item_done = False

        content_without_toggler = re.sub(
            r'\[toggler[^\]]*\].*?\[/toggler\]', '', slot_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        for table_match in re.finditer(r'\[table\](.*?)\[/table\]', content_without_toggler, re.DOTALL | re.IGNORECASE):
            rows = parse_bbcode_table_rows(table_match.group(1))
            items, slot_first_item_done = process_bbcode_table_rows(
                rows, in_toggler=False, slot_first_item_done=slot_first_item_done,
                debug_spec=spec_key if debug else None, slot_name=slot_name
            )
            for item_id, status in items.items():
                if item_id not in result:
                    result[item_id] = status

        for toggler_match in re.finditer(r'\[toggler[^\]]*\](.*?)\[/toggler\]', slot_content, re.DOTALL | re.IGNORECASE):
            toggler_content = toggler_match.group(1)
            for table_match in re.finditer(r'\[table\](.*?)\[/table\]', toggler_content, re.DOTALL | re.IGNORECASE):
                rows = parse_bbcode_table_rows(table_match.group(1))
                items, _ = process_bbcode_table_rows(
                    rows, in_toggler=True, slot_first_item_done=slot_first_item_done,
                    debug_spec=spec_key if debug else None, slot_name=slot_name
                )
                for item_id, status in items.items():
                    if item_id not in result:
                        result[item_id] = status

    return result


# ---------------------------------------------------------------------------
# Парсинг HTML таблиц (старые страницы Wowhead типа karazhan-best-in-slot)
# Логика взята из рабочего оригинала v1.5 с добавлением статусов
# ---------------------------------------------------------------------------
def parse_html_tables(html_text, spec_short):
    """
    spec_short — короткое имя спека без класса: "arms", "fury", "fire" и т.д.
    Нужно для особой логики воина.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    tables = soup.find_all("table")
    result = {}

    for table in tables:
        is_further_option = False
        is_two_handed_sword = False

        prev_node = table.find_previous(["h2", "h3"])
        table_title = prev_node.text.lower() if prev_node else ""

        if spec_short == "arms" and "two-hand" in table_title and "sword" in table_title:
            is_two_handed_sword = True

        # Проверка заголовка и ближайшего текста над таблицей
        # Further Options = таблица под "further options", "honorable mention" и похожими фразами
        further_option_keywords = [
            "further options", "honorable mention", "honorable mentions",
            "other recommendation", "other option", "additional option",
            "also consider", "budget option", "budget alternative",
        ]
        if any(kw in table_title for kw in further_option_keywords):
            is_further_option = True
        else:
            # Проверяем ближайшие текстовые узлы над таблицей (параграфы, не только заголовки)
            text_nodes_before = table.find_all_previous(string=True)
            for node in text_nodes_before[:8]:
                node_text = node.strip().lower()
                if not node_text:
                    continue
                if any(kw in node_text for kw in further_option_keywords):
                    is_further_option = True
                    break
                # Если дошли до заголовка другого слота — останавливаемся
                parent = node.parent
                if parent and parent.name in ["h2", "h3"]:
                    break

        rows = table.find_all("tr")
        table_first_item_done = False  # первый предмет в этой таблице = Absolute BiS

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            raw_rank = " ".join(cells[0].text.split()).lower()
            if not raw_rank or len(raw_rank) > 60:
                continue
            if any(x in raw_rank for x in ["heroic", "normal", "dungeon", "hc"]):
                continue

            all_links = cells[1].find_all("a")
            local_item_ids = []
            for link in all_links:
                href = link.get("href", "") or ""
                if "item=" in href:
                    m = re.search(r"item=(\d+)", href)
                    if m:
                        local_item_ids.append(int(m.group(1)))

            if not local_item_ids:
                continue

            # Особая логика для воинов — у них ранги именованные (best/great/good)
            # Если ранг не опознан или содержит только приписку — используем позицию
            if spec_short in ["arms", "fury", "protection"]:
                if "easy to obtain" in raw_rank:
                    rank_text = "Sub-BiS (Scryers only)" if "scryers" in raw_rank else "Sub-BiS (Optional)"
                elif "crafted alternative" in raw_rank:
                    rank_text = "Sub-BiS Crafted Alternative"
                elif "mitigation alternative" in raw_rank:
                    rank_text = "Sub-BiS Mitigation Alternative"
                elif "threat alternative" in raw_rank:
                    rank_text = "Sub-BiS Threat Alternative"
                elif "hit alternative" in raw_rank:
                    rank_text = "Sub-BiS if you need Hit"
                elif "good" in raw_rank or "optional" in raw_rank:
                    rank_text = "Sub-BiS (Optional)"
                elif "best threat" in raw_rank:
                    rank_text = "Close to BiS (Best Threat)"
                elif "slow alternative" in raw_rank:
                    rank_text = "Close to BiS (Slow Alternative)"
                elif "fast alternative" in raw_rank:
                    rank_text = "Close to BiS (Fast Alternative)"
                elif "great" in raw_rank:
                    rank_text = "Close to BiS (Orc)" if "orc" in raw_rank else "Close to BiS"
                elif "best (hard)" in raw_rank:
                    rank_text = "Close to BiS"
                elif "best" in raw_rank:
                    # best overall / best / p1 bis — Absolute BiS
                    rank_text = "Absolute BiS"
                    table_first_item_done = True
                else:
                    # Только приписка без явного ранга — определяем по позиции
                    if not table_first_item_done:
                        rank_text = "Absolute BiS"
                        table_first_item_done = True
                    else:
                        rank_text = "Close to BiS"
            else:
                # Стандартная логика для всех остальных классов:
                # наличие "bis" в ранге определяет BiS-уровень, отсутствие — Sub-BiS (Optional)
                if is_further_option:
                    rank_text = "Sub-BiS Further Options"
                elif "bis" in raw_rank:
                    if "hit" in raw_rank:
                        rank_text = "BiS if you need Hit"
                    elif "jc" in raw_rank or "jewelcrafting" in raw_rank:
                        rank_text = "BiS if you do Jewelcrafting"
                    elif "demon" in raw_rank:
                        rank_text = "BiS Against Demons"
                    elif not table_first_item_done:
                        rank_text = "Absolute BiS"
                        table_first_item_done = True
                    else:
                        rank_text = "Close to BiS"
                else:
                    rank_text = "Sub-BiS (Optional)"

            if is_two_handed_sword and rank_text == "Absolute BiS":
                rank_text = "Absolute BiS (With Sword Spec Talented)"

            for item_id in local_item_ids:
                result[item_id] = rank_text

    return result


# ---------------------------------------------------------------------------
# Парсинг Icy Veins (только для arms/fury воина)
# Одна страница, переключение фаз через #area_1 / #area_2
# ---------------------------------------------------------------------------
def parse_icy_veins(url, spec_short, phase, target_area=None):
    print(f"  [Icy Veins] Парсим: {spec_short} — {phase} (area: {target_area})...")
    items = {}

    if not url:
        return items

    try:
        response = requests.get(url, impersonate="chrome", timeout=30)
        if response.status_code != 200:
            print(f"    (!) Ошибка доступа: {response.status_code}")
            return items

        soup = BeautifulSoup(response.text, "html.parser")

        if target_area:
            container = soup.find("div", id=target_area) or soup
        else:
            container = soup

        tables = container.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                all_links = cells[1].find_all("a")
                for link in all_links:
                    href = link.get("href", "") or ""
                    if "item=" in href:
                        m = re.search(r"item=(\d+)", href)
                        if m:
                            items[int(m.group(1))] = "Absolute BiS"

    except Exception as e:
        print(f"    (!) Ошибка Icy Veins {spec_short} {phase}: {e}")

    print(f"    -> Найдено предметов: {len(items)}")
    return items


# ---------------------------------------------------------------------------
# Основная функция парсинга страницы Wowhead
# ---------------------------------------------------------------------------
def parse_page(url, spec_key, phase):
    """
    Пробует два формата:
    1. Новый: BBCode в <script id="data.{guid}"> (страницы /classes/...)
    2. Старый: HTML таблицы (страницы karazhan-best-in-slot и т.п.)
    """
    print(f"  [Wowhead] Парсим: {spec_key} — {phase} ...")
    items = {}

    # spec_short — часть до первого "_" ("fire" из "fire_mage", "arms" из "arms_warrior")
    spec_short = spec_key.split("_")[0]

    try:
        response = requests.get(url, impersonate="chrome", timeout=30)
        if response.status_code != 200:
            print(f"    (!) Ошибка доступа: {response.status_code}")
            return items

        html = response.text

        bbcode = extract_bbcode(html)
        if bbcode:
            print(f"    [формат: BBCode]")
            if isinstance(bbcode, str):
                tags = set(re.findall(r'\[(/?\w+)', bbcode))
                idx = bbcode.find('[item=')
                snippet = bbcode[max(0,idx-200):idx+50] if idx >= 0 else ''
                print(f"    [DEBUG tags={sorted(tags)} snippet_before_item={repr(snippet)}]")
            items = parse_bbcode(bbcode, spec_key=spec_key)
            if spec_key == 'arcane_mage':
                import sys; sys.exit(0)
        else:
            print(f"    [формат: HTML таблицы]")
            items = parse_html_tables(html, spec_short)

        if not items:
            print(f"    (!) Найдено 0 предметов")

    except Exception as e:
        print(f"    (!) Ошибка парсинга {spec_key} {phase}: {e}")

    print(f"    -> Найдено предметов: {len(items)}")
    return items


# ---------------------------------------------------------------------------
# URL-ы всех классов и спеков
# Ключи: {spec}_{class} — важно для избежания коллизий (restoration_shaman vs restoration_druid)
# P1 URL-ы используют именованные karazhan-страницы (старый формат HTML таблиц)
# ---------------------------------------------------------------------------
URLS = {
    "mage": {
        "arcane_mage": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/mage/arcane/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/arcane-mage-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/mage/arcane/dps-bis-gear-pve-phase-2",
        },
        "fire_mage": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/mage/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/fire-mage-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/mage/fire/dps-bis-gear-pve-phase-2",
        },
        "frost_mage": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/mage/frost/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/frost-mage-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/mage/frost/dps-bis-gear-pve-phase-2",
        },
    },

    "priest": {
        "shadow_priest": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/priest/shadow/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/shadow-priest-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/priest/shadow/dps-bis-gear-pve-phase-2",
        },
        "holy_priest": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/priest/healer-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/priest-healer-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/priest/healer-bis-gear-pve-phase-2",
        },
    },

    "warlock": {
        "affliction_warlock": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/warlock/affliction/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/affliction-warlock-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/warlock/affliction/dps-bis-gear-pve-phase-2",
        },
        "demonology_warlock": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/warlock/demonology/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/demonology-warlock-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/warlock/demonology/dps-bis-gear-pve-phase-2",
        },
        "destruction_warlock": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/warlock/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/destruction-warlock-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/warlock/destruction/dps-bis-gear-pve-phase-2",
        },
    },

    "druid": {
        "balance_druid": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/druid/balance/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/balance-druid-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/druid/balance/dps-bis-gear-pve-phase-2",
        },
        "feral_druid": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/druid/feral/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/feral-druid-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/druid/feral/dps-bis-gear-pve-phase-2",
        },
        "feral_tank_druid": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/druid/feral/tank-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/feral-druid-tank-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/druid/feral/tank-bis-gear-pve-phase-2",
        },
        "restoration_druid": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/druid/healer-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/druid-healer-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/druid/healer-bis-gear-pve-phase-2",
        },
    },

    "shaman": {
        "elemental_shaman": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/shaman/elemental/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/elemental-shaman-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/shaman/elemental/dps-bis-gear-pve-phase-2",
        },
        "enhancement_shaman": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/shaman/enhancement/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/enhancement-shaman-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/shaman/enhancement/dps-bis-gear-pve-phase-2",
        },
        "restoration_shaman": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/shaman/healer-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/shaman-healer-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/shaman/healer-bis-gear-pve-phase-2",
        },
    },

    "hunter": {
        "beastmastery_hunter": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/hunter/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/beast-mastery-hunter-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/hunter/beast-mastery/dps-bis-gear-pve-phase-2",
        },
        "survival_hunter": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/hunter/survival/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/survival-hunter-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/hunter/survival/dps-bis-gear-pve-phase-2",
        },
    },

    # Только Combat — единственный viable PvE spec
    "rogue": {
        "combat_rogue": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/rogue/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/rogue-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/rogue/dps-bis-gear-pve-phase-2",
        },
    },

    "warrior": {
        "arms_warrior": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/warrior/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/arms-warrior-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/warrior/arms/dps-bis-gear-pve-phase-2",
        },
        "fury_warrior": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/warrior/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/arms-warrior-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/warrior/fury/dps-bis-gear-pve-phase-2",
        },
        "protection_warrior": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/warrior/protection/tank-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/protection-warrior-tank-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/warrior/protection/tank-bis-gear-pve-phase-2",
        },
    },

    "paladin": {
        "holy_paladin": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/paladin/holy/healer-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/holy-paladin-healer-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/paladin/holy/healer-bis-gear-pve-phase-2",
        },
        "retribution_paladin": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/paladin/retribution/dps-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/retribution-paladin-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/paladin/retribution/dps-bis-gear-pve-phase-2",
        },
        "protection_paladin": {
            "pre": "https://www.wowhead.com/tbc/guide/classes/paladin/tank-bis-gear-pve-pre-raid",
            "p1":  "https://www.wowhead.com/tbc/guide/paladin-tank-karazhan-best-in-slot-gear-burning-crusade-classic-wow",
            "p2":  "https://www.wowhead.com/tbc/guide/classes/paladin/tank-bis-gear-pve-phase-2",
        },
    },
}

# ---------------------------------------------------------------------------
# Ручные патчи статусов — для предметов на старых HTML страницах без иконок
# Формат: { spec_key: { phase: { item_id: status } } }
# Используется для дестро варлока p1, где Shadow/Fire иконок нет в HTML
# ---------------------------------------------------------------------------
MANUAL_PATCHES = {
    "destruction_warlock": {
        "p1": {
            # Fire Destro BiS
            21848: "Absolute BiS - Fire Destro",      # Spellfire Robe
            21847: "Absolute BiS - Fire Destro",      # Spellfire Gloves
            21846: "Absolute BiS - Fire Destro",      # Spellfire Belt
            # Shadow Destro BiS
            28964: "Absolute BiS - Shadow Destro",    # Voidheart Robe
            28963: "Absolute BiS - Shadow Destro",    # Voidheart Crown
            28967: "Absolute BiS - Shadow Destro",    # Voidheart Mantle
            28968: "Absolute BiS - Shadow Destro",    # Voidheart Gloves
            28966: "Close to BiS - Shadow Destro",    # Voidheart Leggings
            # Shadow Destro крафт
            21871: "Close to BiS - Shadow Destro",    # Frozen Shadoweave Robe
            21869: "Close to BiS - Shadow Destro",    # Frozen Shadoweave Shoulders
            21870: "Close to BiS - Shadow Destro",    # Frozen Shadoweave Boots
        },
    },
}

# Icy Veins — только для arms и fury воина
# Одна страница, фазы переключаются через area_1 / area_2
ICY_URLS = {
    "arms_warrior": {
        "pre": ("https://www.icy-veins.com/tbc-classic/arms-warrior-dps-pve-pre-raid-gear", None),
        "p1":  ("https://www.icy-veins.com/tbc-classic/arms-warrior-dps-pve-gear-best-in-slot", "area_1"),
        "p2":  ("https://www.icy-veins.com/tbc-classic/arms-warrior-dps-pve-gear-best-in-slot", "area_2"),
    },
    "fury_warrior": {
        "pre": ("https://www.icy-veins.com/tbc-classic/arms-warrior-dps-pve-pre-raid-gear", None),
        "p1":  ("https://www.icy-veins.com/tbc-classic/arms-warrior-dps-pve-gear-best-in-slot", "area_1"),
        "p2":  ("https://www.icy-veins.com/tbc-classic/arms-warrior-dps-pve-gear-best-in-slot", "area_2"),
    },
}


def main():
    print(f"=== Best BiS Tooltip TBC Parser v{VERSION} ===\n")

    # item_id -> { spec_key -> { phase -> status } }
    master_db = {}

    # --- Этап 1: Wowhead ---
    for char_class, specs in URLS.items():
        print(f"\n[{char_class.upper()}]")
        for spec_key, phases in specs.items():
            for phase, url in phases.items():
                data = parse_page(url, spec_key, phase)
                for item_id, status in data.items():
                    if item_id not in master_db:
                        master_db[item_id] = {}
                    if spec_key not in master_db[item_id]:
                        master_db[item_id][spec_key] = {}
                    if phase not in master_db[item_id][spec_key]:
                        master_db[item_id][spec_key][phase] = status

    # --- Этап 2: Icy Veins (приоритет для arms/fury воина) ---
    print(f"\n[WARRIOR — Icy Veins кросс-проверка]")
    for spec_key, phases in ICY_URLS.items():
        for phase, (url, area) in phases.items():
            spec_short = spec_key.split("_")[0]
            icy_data = parse_icy_veins(url, spec_short, phase, target_area=area)
            for item_id, status in icy_data.items():
                # Icy Veins имеет приоритет — перезаписываем статус
                if item_id not in master_db:
                    master_db[item_id] = {}
                if spec_key not in master_db[item_id]:
                    master_db[item_id][spec_key] = {}
                master_db[item_id][spec_key][phase] = status

    # --- Этап 2.5: Применение ручных патчей ---
    print(f"\n[Применение ручных патчей...]")
    for spec_key, phases in MANUAL_PATCHES.items():
        for phase, items in phases.items():
            for item_id, status in items.items():
                if item_id not in master_db:
                    master_db[item_id] = {}
                if spec_key not in master_db[item_id]:
                    master_db[item_id][spec_key] = {}
                # Патч всегда перезаписывает — он точнее парсера для этих предметов
                master_db[item_id][spec_key][phase] = status
                print(f"  [{spec_key}] item={item_id} {phase} -> {status}")

    # --- Этап 2.6: Нормализация фаз ---
    # Статус не может ухудшаться в более ранней фазе.
    # Порядок приоритета: Absolute BiS > Close to BiS > Sub-BiS (Optional) > Sub-BiS Further Options
    STATUS_RANK = {
        "Absolute BiS": 100,
        "Close to BiS": 80,
        "Sub-BiS (Optional)": 50,
        "Sub-BiS Further Options": 30,
    }

    def get_rank(status):
        if not status:
            return 0
        for key, rank in STATUS_RANK.items():
            if status.startswith(key):
                return rank
        return 40  # прочие статусы (Sub-BiS if you need Hit и т.д.) — между Optional и Further

    PHASE_ORDER = ["p2", "p1", "pre"]  # от новейшей к старейшей

    for item_id, spec_dict in master_db.items():
        for spec_key, phases_data in spec_dict.items():
            # Проход 1: от p2 к pre
            # Если ранняя фаза хуже поздней — поднимаем статус
            # Если ранней фазы нет — создаём с лучшим статусом поздней
            best_status = None
            best_rank = 0
            for phase in PHASE_ORDER:
                if phase in phases_data:
                    current_rank = get_rank(phases_data[phase])
                    if current_rank > best_rank:
                        best_rank = current_rank
                        best_status = phases_data[phase]
                    elif best_status and current_rank < best_rank:
                        phases_data[phase] = best_status
                # Фазы нет в оригинальных данных — не создаём искусственно


    # --- Этап 3: Запись bisdata.lua ---
    output_path = os.path.join(SCRIPT_DIR, "bisdata.lua")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("-- Этот файл сгенерирован автоматически parser_v2.0.py\n")
        f.write("-- Ключи спеков: {spec}_{class} (напр. fire_mage, restoration_druid)\n")
        f.write("BestBisListData = {\n")
        for item_id in sorted(master_db.keys()):
            f.write(f"    [{item_id}] = {{\n")
            for spec_key in sorted(master_db[item_id].keys()):
                phases_data = master_db[item_id][spec_key]
                if phases_data:
                    f.write(f'        ["{spec_key}"] = {{\n')
                    for phase in ["pre", "p1", "p2"]:
                        if phase in phases_data:
                            status = phases_data[phase].replace('"', '\\"')
                            f.write(f'            ["{phase}"] = "{status}",\n')
                    f.write("        },\n")
            f.write("    },\n")
        f.write("}\n")

    total_items = len(master_db)
    total_entries = sum(len(specs) for specs in master_db.values())
    print(f"\n=== Готово! ===")
    print(f"Предметов в базе: {total_items}")
    print(f"Записей спек/предмет: {total_entries}")
    print(f"Файл записан: {output_path}")


if __name__ == "__main__":
    main()
