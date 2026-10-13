"""Casamento de jogos entre as duas APIs (football-data.org e API-Football)."""
import difflib
import re
import unicodedata

STOP = {"fc", "cf", "sc", "ac", "afc", "club", "de", "da", "do", "dos", "the", "cd", "sad", "fk", "sk",
        "ec", "esporte", "futebol", "clube"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t]
    kept = [t for t in toks if t not in STOP]
    return " ".join(kept or toks)


def similarity(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    ta, tb = set(na.split()), set(nb.split())
    jacc = len(ta & tb) / len(ta | tb)
    return max(difflib.SequenceMatcher(None, na, nb).ratio(), jacc)


def pair_score(h1, a1, h2, a2) -> float:
    return (similarity(h1, h2) + similarity(a1, a2)) / 2


def pick(m: dict, rows, min_score: float = 0.25):
    """Escolhe, entre jogos candidatos (mesma liga e horário parecido), o de nomes mais parecidos."""
    scored = sorted(
        ((pair_score(m["home"], m["away"], r["home"], r["away"]), r) for r in rows),
        key=lambda x: -x[0],
    )
    if scored and scored[0][0] >= min_score:
        return scored[0][1]
    return None