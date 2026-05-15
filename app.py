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
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")
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
- "Cena skipasu?" → HLEDAT:skipas cena 2026
Nepoužívej HLEDAT pokud odpověď znáš.
{fakta_text}"""

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

def google_search(query):
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "num": 3}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if "items" not in data:
            return None
        obsah = f"Výsledky pro: {query}\n\n"
        for item in data["items"]:
            obsah += f"• {item.get('title','')}\n{item.get('snippet','')}\n\n"
        try:
            nadpis, text = precti_url(data["items"][0]["link"])
            if text:
                obsah += f"Detail:\n{text[:1500]}"
        except:
            pass
        return obsah
    except Exception as e:
        print(f"Chyba vyhledávání: {e}")
        return None

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

        # Detekuj vyhledávání
        if odpoved.startswith("HLEDAT:"):
            dotaz = odpoved.replace("HLEDAT:", "").strip()
            print(f"🔍 Vyhledávám: {dotaz}")
            vysledky = google_search(dotaz)
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
