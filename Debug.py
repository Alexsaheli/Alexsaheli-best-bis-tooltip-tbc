from curl_cffi import requests
import re

url = "https://www.wowhead.com/tbc/guide/mage-dps-karazhan-best-in-slot-gear-burning-crusade-classic-wow"
response = requests.get(url, impersonate="chrome", timeout=30)
html = response.text

# Берём второй printHtml и показываем конец строки — нужно найти закрывающую скобку
idx = html.find("printHtml", html.find("printHtml") + 1)
chunk = html[idx:idx+50000]

# Ищем конец вызова — ", "что-то" на конце
end_match = re.search(r'",\s*"([^"]+)"\s*\)', chunk)
if end_match:
    print("Второй аргумент:", end_match.group(1))
    print("Контекст конца вызова:", chunk[end_match.start()-50:end_match.end()+50])
else:
    print("Конец не найден, последние 300 символов chunk:")
    print(chunk[-300:])