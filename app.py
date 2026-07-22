import os, json, time, uuid, datetime, pathlib
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE = DATA_DIR / "state.json"
HIST = DATA_DIR / "history.json"

# ---- LLM config (OpenAI-compatible ; défaut = groslolo/gemma4) ----
LLM_BASE = os.environ.get("OLLAMA_HOST", "http://100.77.245.32:11434").rstrip("/")
LLM_FALLBACK = os.environ.get("OLLAMA_FALLBACK_HOST", "http://100.80.237.65:11434").rstrip("/")
LLM_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:latest")
LLM_KEY = os.environ.get("OLLAMA_API_KEY", "")   # clé Ollama online (Authorization Bearer)
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

COLS = ["todo", "doing", "done"]
COL_LABELS = {"todo": "À faire", "doing": "En cours", "done": "Fait"}

def _card(title, desc="", tag=""):
    return {"id": uuid.uuid4().hex[:8], "title": title, "desc": desc, "tag": tag}

def seed():
    return {
        "boards": {
            "arnaud": {"name": "Arnaud", "columns": {
                "todo": [_card("Bootstrap venvs cabane", "uv sync sur la cabane", "infra")],
                "doing": [_card("Kanban partagé", "3 tableaux + IA", "produit")],
                "done": [_card("Cabane + Claude Code", "token 1 an, PATH persistant", "infra"),
                         _card("Cockpit + aperçus", "iframes + boutons déployer", "infra"),
                         _card("HTTPS partout", "", "infra")],
            }},
            "charles": {"name": "Charles", "columns": {
                "todo": [], "doing": [_card("Staging Charles", "rasa-staging-charles", "dev")], "done": []}},
            "commun": {"name": "Commun", "columns": {
                "todo": [_card("Poser la clé OVH AI Endpoints", "clé actuelle rejetée", "ia")],
                "doing": [_card("Front public par staging", "optionnel", "produit"),
                          _card("Cockpit — toutes les fonctions", "en cours", "produit")],
                "done": [_card("Hermès autonome (chat + mémoire)", "", "ia"),
                         _card("HTTPS partout", "", "infra")],
            }},
        },
        "updated": time.time(),
    }

def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    s = seed()
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))
    return s

def save_state(s):
    s["updated"] = time.time()
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))

def load_history():
    if HIST.exists():
        try:
            return json.loads(HIST.read_text())
        except Exception:
            pass
    return []

def add_history(entry):
    h = load_history()
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    h.insert(0, entry)
    HIST.write_text(json.dumps(h[:500], ensure_ascii=False, indent=2))

def _index(state):
    # map card id -> (board, col, title)
    m = {}
    for bk, b in state.get("boards", {}).items():
        for ck, cards in b.get("columns", {}).items():
            for c in cards:
                m[c["id"]] = (bk, ck, c.get("title", ""))
    return m

def diff_history(old, new, who):
    o, n = _index(old), _index(new)
    for cid, (bk, ck, title) in n.items():
        if cid not in o:
            add_history({"who": who, "action": "ajout", "title": title,
                         "detail": f"{new['boards'][bk]['name']} · {COL_LABELS.get(ck, ck)}"})
        else:
            ob, oc, _ = o[cid]
            if (ob, oc) != (bk, ck):
                add_history({"who": who, "action": "déplacé", "title": title,
                             "detail": f"{old['boards'][ob]['name']}/{COL_LABELS.get(oc, oc)} → {new['boards'][bk]['name']}/{COL_LABELS.get(ck, ck)}"})
    for cid, (bk, ck, title) in o.items():
        if cid not in n:
            add_history({"who": who, "action": "supprimé", "title": title,
                         "detail": f"{old['boards'][bk]['name']} · {COL_LABELS.get(ck, ck)}"})

app = FastAPI(title="Kanban RASA")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/state")
def get_state():
    return load_state()

@app.put("/api/state")
async def put_state(request: Request):
    body = await request.json()
    who = body.get("who", "?")
    new = body.get("state") or body
    old = load_state()
    save_state(new)
    try:
        diff_history(old, new, who)
    except Exception:
        pass
    return {"ok": True, "updated": new.get("updated")}

@app.get("/api/history")
def get_history():
    return load_history()

def _prompt(board_name, cards, context):
    txt = "\n".join(f"- [{COL_LABELS.get(c[1],c[1])}] {c[0]}" for c in cards) or "(vide)"
    return (
        "Tu es un chef de projet pour l'équipe RASA (art indien, scraping, ML, dashboard).\n"
        f"Tableau: {board_name}. Cartes actuelles:\n{txt}\n\n"
        f"Contexte dépôts git:\n{context or '(non fourni)'}\n\n"
        "Propose 3 à 5 NOUVELLES tâches concrètes et utiles, non déjà listées. "
        "Réponds UNIQUEMENT en JSON: "
        '[{"title":"...","desc":"...","column":"todo|doing|done"}]'
    )

OVH_BASE  = os.environ.get("RASA_OVH_AI_BASE", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1").rstrip("/")
OVH_KEY   = os.environ.get("RASA_OVH_AI_KEY", "")
OVH_MODEL = os.environ.get("RASA_OVH_AI_MODEL", "gpt-oss-120b")

async def _ovh(prompt):
    """OVH AI Endpoints (OpenAI-compatible). Hebergement europeen, compte Arnaud."""
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{OVH_BASE}/chat/completions",
                         headers={"Authorization": f"Bearer {OVH_KEY}"},
                         json={"model": OVH_MODEL,
                               "messages": [{"role": "user", "content": prompt}],
                               "temperature": 0.3, "max_tokens": 1500})
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        # gpt-oss est un modele a raisonnement : si content est vide, le JSON peut etre
        # dans le champ de raisonnement.
        return msg.get("content") or msg.get("reasoning_content") or ""

async def _ollama(base, prompt):
    headers = {"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else {}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{base}/api/generate", headers=headers,
                         json={"model": LLM_MODEL, "prompt": prompt, "stream": False})
        r.raise_for_status()
        return r.json().get("response", "")

async def _gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def _parse_json(txt):
    import re
    m = re.search(r"\[.*\]", txt, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    out = []
    for it in arr if isinstance(arr, list) else []:
        if isinstance(it, dict) and it.get("title"):
            col = it.get("column", "todo")
            out.append({"title": str(it["title"])[:120], "desc": str(it.get("desc", ""))[:240],
                        "column": col if col in COLS else "todo"})
    return out

@app.post("/api/ai/suggest")
async def ai_suggest(request: Request):
    body = await request.json()
    bn = body.get("board_name", "?")
    cards = body.get("cards", [])
    context = body.get("context", "")
    prompt = _prompt(bn, cards, context)
    if OVH_KEY:                                    # 1er choix : OVH AI Endpoints (Europe)
        try:
            out = _parse_json(await _ovh(prompt))
            if out:
                return {"ok": True, "cards": out, "via": "ovh:" + OVH_MODEL}
        except Exception:
            pass
    for base in (LLM_BASE, LLM_FALLBACK):
        try:
            return {"ok": True, "cards": _parse_json(await _ollama(base, prompt)), "via": base}
        except Exception:
            continue
    if GEMINI_KEY:
        try:
            return {"ok": True, "cards": _parse_json(await _gemini(prompt)), "via": "gemini"}
        except Exception as e:
            return {"ok": False, "error": f"gemini: {e}", "cards": []}
    return {"ok": False, "error": "IA injoignable (groslolo/Gemini). Configure OLLAMA_HOST ou GEMINI_API_KEY.", "cards": []}

@app.get("/")
def root():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
