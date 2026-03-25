# ♟️ Pro Game Review — Full Stack

Frontend → **GitHub Pages**  
Backend  → **Railway / Render / Fly.io** (free tiers work)

---

## Architecture

```
Chess.com API
     │  PGN fetch (from browser)
     ▼
┌──────────────────────┐        ┌────────────────────────────┐
│  Frontend            │───────▶│  Backend (FastAPI + Python) │
│  GitHub Pages        │  HTTPS │  Stockfish 16, depth 20-22  │
│  index.html          │◀───────│  /analyze/stream  (NDJSON)  │
│                      │        │  /analyze/move    (JSON)    │
└──────────────────────┘        └────────────────────────────┘
```

**Two flows:**

| Flow | How it works |
|------|-------------|
| Load from history | Browser fetches PGN from Chess.com → sends full PGN to `/analyze/stream` → backend streams results move-by-move |
| Manual play | User plays a move on the board → browser sends `{fen, move_uci}` to `/analyze/move` → backend returns eval + classification instantly |

---

## 1 — Deploy Backend

### Option A: Railway (recommended, free tier)

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Push the `backend/` folder to a GitHub repo (or the whole project)
3. Railway auto-detects the Dockerfile
4. Set environment variables in Railway dashboard:
   ```
   STOCKFISH_PATH = /usr/games/stockfish
   SF_THREADS     = 2
   SF_HASH        = 256
   ```
5. Copy the generated URL, e.g. `https://chess-analysis.up.railway.app`

### Option B: Render (also free)

1. Go to [render.com](https://render.com) → New → Web Service → connect GitHub repo
2. Set **Root Directory** to `backend`
3. Build command: `pip install -r requirements.txt && apt-get install -y stockfish`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Run locally (for testing)

```bash
cd backend
pip install -r requirements.txt
# Install Stockfish:
#   Mac:   brew install stockfish
#   Linux: apt-get install stockfish
uvicorn main:app --reload
# → http://localhost:8000
```

---

## 2 — Deploy Frontend to GitHub Pages

1. Edit `frontend/index.html` line 7:
   ```js
   window.API = "https://YOUR-BACKEND.railway.app";
   ```

2. Push `frontend/` to GitHub

3. Go to repo **Settings → Pages → Source → main branch / root or /frontend folder**

4. Your app is live at `https://yourusername.github.io/repo-name`

---

## API Reference

### `POST /analyze/stream`
Streams analysis for a full game.

**Request:**
```json
{ "pgn": "1. e4 e5 ...", "depth": 20 }
```

**Response** (NDJSON — one line per move):
```json
{"index":0,"total":42,"san":"e4","uci":"e2e4","fen":"...","eval":0.3,
 "classification":{"id":"★","class":"c-best","label":"Best","text":"is the Best move","acc":100,"eval_loss":0.0,"bestMove":null}}
```

### `POST /analyze/move`
Analyzes a single manually-played move.

**Request:**
```json
{ "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", "move_uci": "e7e5", "depth": 20 }
```

**Response:**
```json
{"san":"e5","uci":"e7e5","fen":"...","eval":-0.1,"eval_before":0.3,
 "classification":{"id":"★","class":"c-best","label":"Best",...}}
```

---

## Classification Scale (matches Chess.com)

| Label | CP Loss | Symbol |
|-------|---------|--------|
| Brilliant | < -30 (eval improved) | !! |
| Best | < 10 | ★ |
| Great | < 25 | ✔ |
| Good | < 60 | ✔ |
| Inaccuracy | < 120 | ?! |
| Mistake | < 200 | ? |
| Blunder | ≥ 200 | ?? |
