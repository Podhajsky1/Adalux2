from flask import Flask, request, jsonify, send_from_directory
import anthropic
import json
import os
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__, static_folder='.', static_url_path='')

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_KEY", "")
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
- Pro jízdní řády doporučíš idos.cz
- Odpovídáš jazykem turisty
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
    except Exception as e:
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
        nadpis, obsah = precti_url(url)
        if obsah:
            zprava = f"Přečetla jsem stránku: {nadpis}\nObsah: {obsah}\n\nShrň ji stručně."

    try:
        messages = historie + [{"role": "user", "content": zprava}]
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=get_system_prompt(),
            messages=messages
        )
        return jsonify({"reply": response.content[0].text})
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
    znalosti["fakta"].append({
        "obsah": data.get("obsah", ""),
        "datum": data.get("datum", "")
    })
    uloz_znalosti(znalosti)
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
