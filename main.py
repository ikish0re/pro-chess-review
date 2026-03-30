from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from analyzer import ChessAnalyzer
import json, asyncio

app = FastAPI(title="Chess Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

analyzer = ChessAnalyzer()


class PGNRequest(BaseModel):
    pgn:       str
    move_time: float = 5.0   # seconds — matches Chess.com default
    num_lines: int   = 3     # MultiPV  — matches Chess.com default


class MoveRequest(BaseModel):
    fen:       str
    move_uci:  str
    move_time: float = 5.0
    num_lines: int   = 3


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze/stream")
async def analyze_stream(body: PGNRequest):
    """
    Streams one JSON line per move (NDJSON).
    Each line:
      {"index":5,"total":40,"san":"Nf3","eval":0.4,
       "classification":{...}}
    """
    async def gen():
        try:
            async for result in analyzer.analyze_pgn_stream(
                body.pgn, body.move_time, body.num_lines
            ):
                yield json.dumps(result) + "\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/analyze/move")
async def analyze_move(body: MoveRequest):
    """Single move evaluation for live play."""
    result = await analyzer.analyze_single_move(
        body.fen, body.move_uci, body.move_time, body.num_lines
    )
    return result
