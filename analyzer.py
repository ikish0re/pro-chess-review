"""
analyzer.py — Chess.com-accurate game analysis.

Matches Chess.com defaults exactly:
  • Stockfish (latest installed)
  • Maximum Time: 3 / 5 / 10 / 20 / 30 sec (or unlimited=0)
  • Number of Lines: 1–5 (default 3)

Brilliant fix:
  Checked BEFORE "exact best move → ★" so a sacrificial best move
  correctly gets !! not ★.
  Requires all three:
    1. Near-best (≤ 10 cp loss)
    2. Genuine sacrifice (lands on attacked square, undefended or over-sac)
    3. Non-obvious (2nd-best line ≥ 100 cp worse)
"""

import chess
import chess.pgn
import chess.engine
import asyncio
import io
import os
from typing import AsyncIterator

STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "/usr/games/stockfish")
SF_THREADS     = int(os.environ.get("SF_THREADS", "2"))
SF_HASH        = int(os.environ.get("SF_HASH",    "256"))

# Depth presets — same as Chess.com's speed tiers
# Chess.com uses depth (not movetime) so simple positions finish instantly
DEPTH_PRESETS = {
    "fast":  16,   # ~0.1–0.5s/move  — blitz review
    "pro":   18,   # ~0.3–1s/move    — Chess.com default
    "gm":    20,   # ~1–3s/move      — deep review
    "elite": 22,   # ~3–8s/move      — max accuracy
}

PV = {
    chess.PAWN: 100, chess.KNIGHT: 305, chess.BISHOP: 333,
    chess.ROOK: 563, chess.QUEEN:  950, chess.KING:  20000,
}

THR_BEST       =  10
THR_GREAT      =  25
THR_GOOD       =  60
THR_INACCURACY = 120
THR_MISTAKE    = 200
BRILLIANT_GAP  = 100


def pov_to_white(pov: chess.engine.PovScore) -> float:
    w = pov.white()
    if w.is_mate():
        return 10.0 if w.mate() > 0 else -10.0
    return round(w.score() / 100.0, 3)


def cp_loss(eval_before: float, eval_after: float, turn: chess.Color) -> int:
    raw = (eval_before - eval_after) if turn == chess.WHITE else (eval_after - eval_before)
    return int(max(-500.0, min(raw * 100, 2000.0)))


def is_sacrifice(board: chess.Board, move: chess.Move) -> bool:
    after = board.copy()
    after.push(move)
    dest  = move.to_square
    piece = after.piece_at(dest)
    if not piece:
        return False
    opp = not board.turn
    if not after.is_attacked_by(opp, dest):
        return False
    moved_val = PV.get(piece.piece_type, 0)
    cap       = board.piece_at(move.to_square)
    cap_val   = PV.get(cap.piece_type, 0) if cap else 0
    is_hanging  = not after.is_attacked_by(board.turn, dest)
    is_over_sac = moved_val > cap_val + 100
    return is_hanging or is_over_sac


def is_non_obvious(mpv: list, turn: chess.Color) -> bool:
    if len(mpv) < 2:
        return True
    gap = (mpv[0] - mpv[1]) * 100 if turn == chess.WHITE else (mpv[1] - mpv[0]) * 100
    return gap >= BRILLIANT_GAP


def classify(board_before, move, san, eval_before, eval_after, best_uci, mpv_scores):
    turn = board_before.turn
    lcp  = cp_loss(eval_before, eval_after, turn)

    if san.endswith("#"):
        return _mk("c-best", "#", "is Checkmate! 🏆", 100, 0, None)

    # Brilliant BEFORE exact-best-move check
    if lcp <= THR_BEST and is_sacrifice(board_before, move) and is_non_obvious(mpv_scores, turn):
        return _mk("c-brilliant", "!!", "is Brilliant!!", 100, lcp, None)

    best_san = None
    if best_uci:
        try:
            best_san = board_before.san(chess.Move.from_uci(best_uci))
        except Exception:
            pass

    if san == best_san:
        return _mk("c-best", "★", "is the Best move", 100, lcp, None)

    if   lcp <= THR_BEST:       cls, sym, label, acc = "c-best",       "★",  "Best",        100
    elif lcp <= THR_GREAT:      cls, sym, label, acc = "c-great",      "✔",  "Great",         95
    elif lcp <= THR_GOOD:       cls, sym, label, acc = "c-good",       "✔",  "Good",          88
    elif lcp <= THR_INACCURACY: cls, sym, label, acc = "c-inaccuracy", "?!", "Inaccuracy",    70
    elif lcp <= THR_MISTAKE:    cls, sym, label, acc = "c-mistake",    "?",  "Mistake",       45
    else:                       cls, sym, label, acc = "c-blunder",    "??", "Blunder",       20

    text = f"is {label}" if cls == "c-good" else f"is a {label}"
    if lcp > THR_GOOD and best_san:
        text += f". Better was <b>{best_san}</b>"

    return _mk(cls, sym, text, acc, lcp, best_san if lcp > THR_GOOD else None)


def _mk(cls, sym, text, acc, lcp, best_move):
    return {"id": sym, "class": cls, "text": text, "acc": acc,
            "eval_loss": round(lcp / 100, 2), "bestMove": best_move}


class ChessAnalyzer:
    def __init__(self):
        self._engine = None

    async def _get_engine(self):
        if self._engine is None:
            _, self._engine = await chess.engine.popen_uci(STOCKFISH_PATH)
            await self._engine.configure({"Threads": SF_THREADS, "Hash": SF_HASH})
        return self._engine

    async def _analyse(self, engine, board: chess.Board,
                       depth: int, num_lines: int) -> tuple:
        """
        Depth-based analysis — stops as soon as target depth is reached.
        This is how Chess.com works: fast on simple positions, thorough
        on complex ones, without wasting time on forced moves.
        """
        limit   = chess.engine.Limit(depth=depth)
        results = await engine.analyse(board, limit, multipv=num_lines)
        if not isinstance(results, list):
            results = [results]
        mpv_scores = [pov_to_white(r["score"]) for r in results]
        pv         = results[0].get("pv", []) if results else []
        best_uci   = pv[0].uci() if pv else None
        return mpv_scores[0] if mpv_scores else 0.0, mpv_scores, best_uci

    async def analyze_pgn_stream(self, pgn_text: str,
                                  depth: int = 18,
                                  num_lines: int = 3) -> AsyncIterator[dict]:
        engine = await self._get_engine()
        game   = chess.pgn.read_game(io.StringIO(pgn_text))
        if game is None:
            raise ValueError("Invalid PGN")

        board = game.board()
        moves = list(game.mainline_moves())
        total = len(moves)

        for idx, move in enumerate(moves):
            turn         = board.turn
            san          = board.san(move)
            board_before = board.copy()

            # Analyse BEFORE — get MultiPV scores + best_uci
            eval_before, mpv_scores, best_uci = await self._analyse(
                engine, board, depth, num_lines)

            board.push(move)

            # Analyse AFTER — single line is enough
            eval_after, _, _ = await self._analyse(engine, board, depth, 1)

            rating = classify(board_before, move, san,
                              eval_before, eval_after, best_uci, mpv_scores)

            yield {
                "index":          idx,
                "total":          total,
                "san":            san,
                "uci":            move.uci(),
                "fen":            board.fen(),
                "eval":           round(eval_after, 2),
                "classification": rating,
            }

            await asyncio.sleep(0)

    async def analyze_single_move(self, fen: str, move_uci: str,
                                   depth: int = 18,
                                   num_lines: int = 3) -> dict:
        engine       = await self._get_engine()
        board        = chess.Board(fen)
        board_before = board.copy()
        move         = chess.Move.from_uci(move_uci)
        san          = board.san(move)

        eval_before, mpv_scores, best_uci = await self._analyse(
            engine, board, depth, num_lines)

        board.push(move)
        eval_after, _, _ = await self._analyse(engine, board, depth, 1)

        rating = classify(board_before, move, san,
                          eval_before, eval_after, best_uci, mpv_scores)

        return {
            "san":         san, "uci": move_uci,
            "fen":         board.fen(),
            "eval":        round(eval_after, 2),
            "eval_before": round(eval_before, 2),
            "classification": rating,
        }
