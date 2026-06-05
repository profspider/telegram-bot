import os
import sqlite3
import requests
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========== CONFIGURAZIONE ==========
BOT_TOKEN = "FINTOoUMr8bCq_co"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DB_FILE = "promemoria.db"

MESI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
GIORNI = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']

# ========== DATABASE ==========
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Tabella principale promemoria
    c.execute('''CREATE TABLE IF NOT EXISTS promemoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        testo TEXT,
        gg INTEGER, mm INTEGER, aa INTEGER,
        ore INTEGER, minuti INTEGER,
        ripeti TEXT,
        intervallo INTEGER,
        ogni_x_anni INTEGER,
        ripeti_avviso INTEGER,
        foto_id TEXT,
        inserito_il TEXT
    )''')
    # Storico segnalazioni
    c.execute('''CREATE TABLE IF NOT EXISTS promemoria_storico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        testo TEXT,
        visto TEXT DEFAULT 'N'
    )''')
    # Nuovi utenti
    c.execute('''CREATE TABLE IF NOT EXISTS promemoria_nuovi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        newold TEXT, data TEXT, tipo TEXT, testo TEXT, chat_id INTEGER
    )''')
    # Limiti marea
    c.execute('''CREATE TABLE IF NOT EXISTS marea_limiti (
        id INTEGER PRIMARY KEY DEFAULT 1,
        cm INTEGER DEFAULT 110
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS marea_utenti (
        chat_id INTEGER PRIMARY KEY,
        cm INTEGER
    )''')
    conn.commit()
    conn.close()

def invia(chat_id, testo):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", 
                     json={"chat_id": chat_id, "text": testo, "parse_mode": "HTML"},
                     timeout=5)
    except:
        pass

def invia_foto(chat_id, foto_id, caption=""):
    try:
        requests.post(f"{TELEGRAM_API}/sendPhoto",
                     json={"chat_id": chat_id, "photo": foto_id, "caption": caption, "parse_mode": "HTML"},
                     timeout=5)
    except:
        pass

def accenti(text):
    mappe = {"à": "a'", "è": "e'", "é": "e'", "ì": "i'", "ò": "o'", "ù": "u'"}
    for k, v in mappe.items():
        text = text.replace(k, v)
    return text

def afafa(text):
    vocali = {'a': 'afa', 'e': 'efe', 'i': 'ifi', 'o': 'ofo', 'u': 'ufu'}
    return ''.join(vocali.get(c, c) for c in text.lower())

def sistema_minuti(minuti, ore):
    minuti = round(minuti / 10) * 10
    if minuti == 60:
        minuti = 0
        ore += 1
    return minuti, ore

def crea_promemoria(chat_id, testo, ripeti, gg, mm, aa, ore, minuti, intervallo, ogni_x_anni, ripeti_avviso, foto_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO promemoria 
        (chat_id, testo, gg, mm, aa, ore, minuti, ripeti, intervallo, ogni_x_anni, ripeti_avviso, foto_id, inserito_il)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (chat_id, testo, gg, mm, aa, ore, minuti, ripeti, intervallo, ogni_x_anni, ripeti_avviso, foto_id, datetime.now().isoformat()))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Notifica admin
    if chat_id not in [182788155, 659909901]:
        invia(182788155, f"➕ Nuovo promemoria #{new_id} da {chat_id}: {testo[:50]}...")
    return new_id

def cancella_promemoria(chat_id, id_prom):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM promemoria WHERE id=? AND chat_id=?", (id_prom, chat_id))
    eliminato = c.rowcount > 0
    conn.commit()
    conn.close()
    return eliminato

def emetti_tutti(chat_id, solo_miei=True):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if solo_miei:
        c.execute("SELECT id, testo, gg, mm, ore, minuti, ripeti FROM promemoria WHERE chat_id=? ORDER BY ripeti, mm, gg", (chat_id,))
    else:
        c.execute("SELECT id, testo, gg, mm, ore, minuti, ripeti, chat_id FROM promemoria ORDER BY ripeti, mm, gg")
    risultati = c.fetchall()
    conn.close()
    
    if not risultati:
        invia(chat_id, "📭 Nessun promemoria trovato")
        return
    
    msg = f"<b>📋 I tuoi promemoria ({len(risultati)})</b>\n\n"
    for r in risultati:
        msg += f"📌 #{r[0]}: {r[1]}"
        if r[2]:
            msg += f" (il {r[2]}/{r[3]}"
            if r[4] != 8 or r[5] != 0:
                msg += f" alle {r[4]:02d}:{r[5]:02d}"
            msg += ")"
        msg += f" [{r[6]}]\n"
        if len(msg) > 3500:
            invia(chat_id, msg)
            msg = ""
    if msg:
        invia(chat_id, msg)

def emetti_oggi(chat_id):
    oggi = datetime.now()
    gg, mm = oggi.day, oggi.month
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, testo FROM promemoria WHERE chat_id=? AND gg=? AND (mm=? OR mm=0)", (chat_id, gg, mm))
    risultati = c.fetchall()
    conn.close()
    
    if not risultati:
        invia(chat_id, "📭 Nessun promemoria per oggi")
        return
    
    msg = f"<b>📅 Promemoria per oggi {gg}/{mm}</b>\n\n"
    for r in risultati:
        msg += f"✅ #{r[0]}: {r[1]}\n"
    invia(chat_id, msg)

def cerca_promemoria(chat_id, lemmi, relazione="AND"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    condizioni = []
    params = [chat_id]
    for lemma in lemmi.split():
        condizioni.append("testo LIKE ?")
        params.append(f"%{lemma}%")
    sql = f"SELECT id, testo, gg, mm FROM promemoria WHERE chat_id=? AND ({f' {relazione} '.join(condizioni)}) ORDER BY mm, gg"
    c.execute(sql, params)
    risultati = c.fetchall()
    conn.close()
    
    if not risultati:
        invia(chat_id, f"🔍 Nessun risultato per: {lemmi}")
        return
    
    msg = f"<b>🔍 Ricerca: {lemmi} ({relazione})</b>\n\n"
    for r in risultati:
        msg += f"📌 #{r[0]}: {r[1]} (il {r[2]}/{r[3]})\n"
    invia(chat_id, msg)

def marea_venezia(chat_id):
    try:
        data = requests.get("http://dati.venezia.it/sites/default/files/dataset/opendata/livello.json", timeout=5).json()
        msg = "🌊 <b>MAREA Venezia</b>\n\n"
        for s in data[:3]:
            cm = s["valore"] * 100
            ora = datetime.fromisoformat(s["data"]).strftime("%d/%m %H:%M")
            msg += f"{s['stazione']}: <b>{cm:.0f} cm</b> ({ora})\n"
        invia(chat_id, msg)
    except:
        invia(chat_id, "❌ Servizio marea non disponibile")

# ========== WEBHOOK PRINCIPALE ==========
@app.route(f"/webhook/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = request.get_json()
    if not update or "message" not in update:
        return "OK", 200
    
    msg = update["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    username = msg["chat"].get("username", "Utente")
    foto_id = msg["photo"][-1]["file_id"] if "photo" in msg else None
    if foto_id and not text and "caption" in msg:
        text = msg["caption"]
    
    if not text:
        return "OK", 200
    
    text = accenti(text)
    parti = text.split()
    comando = parti[0].upper() if parti else ""
    
    # ========== COMANDI ==========
    if comando == "/START" or text.lower() == "ciao":
        invia(chat_id, f"👋 Ciao {username}! Bot Promemoria.\n/help per i comandi")
        emetti_tutti(chat_id, True)
    
    elif comando == "/HELP":
        help_text = """<b>📚 COMANDI</b>

<b>A</b> ggmm testo → annuale (es: A 1503 Compleanno)
<b>M</b> gg testo → mensile (es: M 25 Bolletta)
<b>F</b> testo → fine mese
<b>N</b> ggmmhhmm testo → una volta
<b>G</b> ggmmhhmm X testo → ogni X giorni
<b>S</b> X testo → tra X minuti
<b>C</b> ID → cancella
<b>T</b> → tutti i promemoria
<b>O</b> → promemoria di oggi
<b>K</b> AND/OR parola1 parola2 → cerca
<b>V</b> → livello marea
<b>U</b> testo → gioco afafa
<b>Autore</b> → info bot"""
        invia(chat_id, help_text)
    
    # A - Annuale
    elif comando == "A" and len(parti) >= 3:
        ggmm = parti[1]
        if len(ggmm) == 4 and ggmm.isdigit():
            gg, mm = int(ggmm[:2]), int(ggmm[2:])
            testo = " ".join(parti[2:])
            if 1 <= mm <= 12 and 1 <= gg <= 31:
                crea_promemoria(chat_id, testo, "a", gg, mm, 0, 8, 0, 0, 0, 0, foto_id)
                invia(chat_id, f"✅ Promemoria annuale il {gg}/{mm}: {testo}")
            else:
                invia(chat_id, "❌ Data non valida")
    
    # M - Mensile
    elif comando == "M" and len(parti) >= 3:
        gg = int(parti[1])
        testo = " ".join(parti[2:])
        if 1 <= gg <= 31:
            crea_promemoria(chat_id, testo, "m", gg, 0, 0, 8, 0, 0, 0, 0)
            invia(chat_id, f"✅ Promemoria il giorno {gg} di ogni mese: {testo}")
    
    # F - Fine mese
    elif comando == "F" and len(parti) >= 2:
        testo = " ".join(parti[1:])
        crea_promemoria(chat_id, testo, "f", 0, 0, 0, 8, 0, 0, 0, 0)
        invia(chat_id, f"✅ Promemoria a fine mese: {testo}")
    
    # N - Una volta
    elif comando == "N" and len(parti) >= 3:
        ggmmhhmm = parti[1]
        if len(ggmmhhmm) == 8 and ggmmhhmm.isdigit():
            gg, mm = int(ggmmhhmm[:2]), int(ggmmhhmm[2:4])
            ore, minuti = int(ggmmhhmm[4:6]), int(ggmmhhmm[6:8])
            minuti, ore = sistema_minuti(minuti, ore)
            testo = " ".join(parti[2:])
            crea_promemoria(chat_id, testo, "n", gg, mm, datetime.now().year, ore, minuti, 0, 0, 0)
            invia(chat_id, f"✅ Promemoria il {gg}/{mm} alle {ore:02d}:{minuti:02d}: {testo}")
    
    # G - Ogni X giorni
    elif comando == "G" and len(parti) >= 4:
        ggmmhhmm = parti[1]
        intervallo = int(parti[2])
        testo = " ".join(parti[3:])
        if len(ggmmhhmm) == 8 and ggmmhhmm.isdigit():
            gg, mm = int(ggmmhhmm[:2]), int(ggmmhhmm[2:4])
            ore, minuti = int(ggmmhhmm[4:6]), int(ggmmhhmm[6:8])
            minuti, ore = sistema_minuti(minuti, ore)
            crea_promemoria(chat_id, testo, "g", gg, mm, datetime.now().year, ore, minuti, intervallo, 0, 0)
            invia(chat_id, f"✅ Promemoria ogni {intervallo} giorni dal {gg}/{mm} alle {ore:02d}:{minuti:02d}")
    
    # S - Tra X minuti
    elif comando == "S" and len(parti) >= 3:
        minuti_s = int(parti[1])
        testo = " ".join(parti[2:])
        data_esec = datetime.now() + timedelta(minutes=minuti_s)
        if data_esec.hour <= 19:
            crea_promemoria(chat_id, testo, "n", data_esec.day, data_esec.month, data_esec.year, data_esec.hour, data_esec.minute, 0, 0, 0)
            invia(chat_id, f"✅ Promemoria tra {minuti_s} minuti alle {data_esec.hour:02d}:{data_esec.minute:02d}")
    
    # C - Cancella
    elif comando == "C" and len(parti) >= 2:
        id_prom = int(parti[1])
        if cancella_promemoria(chat_id, id_prom):
            invia(chat_id, f"✅ Promemoria #{id_prom} cancellato")
        else:
            invia(chat_id, f"❌ Promemoria #{id_prom} non trovato o non ti appartiene")
    
    # T - Tutti
    elif comando == "T":
        emetti_tutti(chat_id, True)
    
    # O - Oggi
    elif comando == "O":
        emetti_oggi(chat_id)
    
    # K - Cerca
    elif comando == "K" and len(parti) >= 3:
        rel = parti[1].upper()
        if rel in ["AND", "OR"]:
            lemmi = " ".join(parti[2:])
            cerca_promemoria(chat_id, lemmi, rel)
    
    # V - Marea
    elif comando == "V":
        marea_venezia(chat_id)
    
    # U - Gioco afafa
    elif comando == "U" and len(parti) >= 2:
        frase = " ".join(parti[1:])
        invia(chat_id, f"🎮 <i>Gioco afafa</i>\n\n{frase}\n<b>→</b> {afafa(frase)}")
    
    # Autore
    elif comando == "AUTORE" or text.lower() == "autore":
        invia(chat_id, "🤖 Bot Promemoria\nVersione Python su Render.com\nCreato da @profspider")
    
    else:
        invia(chat_id, "❌ Comando non riconosciuto. /help per aiuto")
    
    return "OK", 200

if __name__ == "__main__":
    init_db()
    print("✅ Database inizializzato")
    
    # Imposta webhook automaticamente su Render
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost")
    webhook_url = f"https://{host}/webhook/{BOT_TOKEN}" if host != "localhost" else f"http://localhost:10000/webhook/{BOT_TOKEN}"
    
    try:
        requests.get(f"{TELEGRAM_API}/setWebhook?url={webhook_url}")
        print(f"✅ Webhook impostato: {webhook_url}")
    except:
        print("⚠️ Webhook da impostare manualmente")
    
    app.run(host="0.0.0.0", port=10000)
