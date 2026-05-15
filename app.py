from flask import Flask, request, jsonify, send_from_directory
import anthropic
import json
import os
import requests
from bs4 import BeautifulSoup
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__, static_folder='.', static_url_path='')

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
ZNALOSTI_FILE = "adalux_znalosti.json"

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def nacti_znalosti():
    if os.path.exists(ZNALOSTI_FILE):
        with open(ZNALOSTI_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"fakta": []}

def uloz_znalosti(data):
    with open(ZNALOSTI_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_system_prompt():
    znalosti = nacti_znalosti()
    fakta_text = ""
    if znalosti["fakta"]:
        fakta_text = "\n\nCO VÍŠ:\n"
        for f in znalosti["fakta"]:
            fakta_text += f"• {f['obsah']}\n"
    return f"""Jsi Adalux – mladá, přátelská a nadšená průvodkyně. Mluvíš přirozeně jako kamarádka.
- Stručné a praktické odpovědi
- Občas emoji ale střídmě
- Odpovídáš jazykem turisty
- Pro jízdní řády doporučíš idos.cz

VYHLEDÁVÁNÍ - pokud nevíš odpověď, použij formát:
HLEDAT:vyhledávací dotaz

Příklady:
- "Kde je lékárna?" → HLEDAT:lékárna Rokytnice nad Jizerou
- "Cena skipasu?" → HLEDAT:skipas Rokytnice cena 2026
Nepoužívej HLEDAT pokud odpověď znáš.
{fakta_text}"""

def duckduckgo_search(query):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}&kl=cz-cs"
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        vysledky = []
        for result in soup.select(".result__body")[:3]:
            titulek = result.select_one(".result__title")
            popis = result.select_one(".result__snippet")
            if titulek and popis:
                vysledky.append({
                    "titulek": titulek.get_text(strip=True),
                    "popis": popis.get_text(strip=True)
                })
        if not vysledky:
            return None
        obsah = f"Výsledky pro: {query}\n\n"
        for v in vysledky:
            obsah += f"• {v['titulek']}\n{v['popis']}\n\n"
        return obsah
    except Exception as e:
        print(f"Chyba vyhledávání: {e}")
        return None

def precti_url(url):
    try:
        if url.startswith("www."):
            url = "https://" + url
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        nadpis = soup.title.string if soup.title else ""
        text = " ".join(soup.get_text(separator=" ", strip=True).split())[:3000]
        return nadpis, text
    except:
        return None, None

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    zprava = data.get("message", "")
    historie = data.get("history", [])

    slova = zprava.split()
    url = next((s for s in slova if s.startswith("http") or s.startswith("www.")), None)
    if url:
        if url.startswith("www."):
            url = "https://" + url
        nadpis, obsah = precti_url(url)
        if obsah:
            zprava = f"Přečetla jsem: {nadpis}\n{obsah}\n\nShrň stručně."

    try:
        messages = historie + [{"role": "user", "content": zprava}]
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=get_system_prompt(),
            messages=messages
        )
        odpoved = response.content[0].text

        if odpoved.startswith("HLEDAT:"):
            dotaz = odpoved.replace("HLEDAT:", "").strip()
            print(f"🔍 Vyhledávám: {dotaz}")
            vysledky = duckduckgo_search(dotaz)
            if vysledky:
                znalosti = nacti_znalosti()
                znalosti["fakta"].append({"obsah": f"{dotaz}: {vysledky[:300]}", "datum": datetime.now().strftime("%d.%m.%Y %H:%M")})
                uloz_znalosti(znalosti)
                nova_zprava = f"{zprava}\n\nNašla jsem:\n{vysledky}"
                messages2 = historie + [{"role": "user", "content": nova_zprava}]
                response2 = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=800,
                    system=get_system_prompt(),
                    messages=messages2
                )
                odpoved = response2.content[0].text

        return jsonify({"reply": odpoved})
    except Exception as e:
        print(f"CHYBA: {e}")
        return jsonify({"reply": f"Chyba: {str(e)}"}), 500

@app.route("/znalosti", methods=["GET"])
def get_znalosti():
    return jsonify(nacti_znalosti())

@app.route("/ucit", methods=["POST"])
def ucit():
    data = request.json
    znalosti = nacti_znalosti()
    znalosti["fakta"].append({"obsah": data.get("obsah", ""), "datum": data.get("datum", "")})
    uloz_znalosti(znalosti)
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
