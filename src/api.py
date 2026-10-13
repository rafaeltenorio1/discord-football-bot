import json
import logging
from datetime import datetime

import aiohttp

log = logging.getLogger("api")


class ApiError(Exception):
    pass


class ApiFootball:
    BASE = "https://v3.football.api-sports.io"

    def __init__(self, key: str, session: aiohttp.ClientSession, timezone: str):
        self.key = key
        self.session = session
        self.timezone = timezone
        self.remaining = None  # requisições restantes hoje

    async def _get(self, path: str, params: dict):
        async with self.session.get(
            f"{self.BASE}{path}",
            headers={"x-apisports-key": self.key},
            params=params,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            data = await r.json()
            left = r.headers.get("x-ratelimit-requests-remaining")
            if left is not None:
                self.remaining = int(left)
            log.info("GET %s %s -> %s (restam %s req hoje)", path, params, r.status, left)
        errors = data.get("errors")
        if errors:  # a API devolve {} ou [] quando está tudo certo
            raise ApiError(str(errors))
        return data.get("response", [])

    async def fixtures_by_date(self, date_iso: str):
        """Todos os jogos do mundo numa data (1 requisição). Filtramos as ligas depois."""
        return await self._get("/fixtures", {"date": date_iso, "timezone": self.timezone})

    async def fixture_detail(self, af_id: int):
        """Um jogo com eventos e estatísticas (1 requisição)."""
        items = await self._get("/fixtures", {"id": af_id, "timezone": self.timezone})
        return items[0] if items else None


def parse_fixture(it: dict) -> dict:
    f, l, t = it["fixture"], it["league"], it["teams"]
    g = it.get("goals") or {}
    detail = None
    if it.get("events") or it.get("statistics"):
        detail = json.dumps(
            {
                "events": it.get("events") or [],
                "statistics": it.get("statistics") or [],
                "referee": f.get("referee"),
            }
        )
    venue = f.get("venue") or {}
    return {
        "af_id": f["id"],
        "fd_id": None,
        "league_id": l["id"],
        "league_name": l.get("name"),
        "league_logo": l.get("logo"),
        "season": l.get("season"),
        "round": l.get("round"),
        "home": t["home"]["name"],
        "home_logo": t["home"].get("logo"),
        "away": t["away"]["name"],
        "away_logo": t["away"].get("logo"),
        "venue": venue.get("name"),
        "city": venue.get("city"),
        "kickoff": f["timestamp"],
        "status": f["status"]["short"],
        "elapsed": f["status"].get("elapsed"),
        "home_goals": g.get("home"),
        "away_goals": g.get("away"),
        "detail": detail,
    }


class FootballData:
    BASE = "https://api.football-data.org/v4"

    def __init__(self, token: str, session: aiohttp.ClientSession):
        self.token = token
        self.session = session

    async def _get(self, path: str, params: dict | None = None):
        async with self.session.get(
            f"{self.BASE}{path}", headers={"X-Auth-Token": self.token}, params=params,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            data = await r.json(content_type=None)
            log.info("GET football-data %s %s -> %s", path, params, r.status)
            if r.status != 200:
                raise ApiError(f"football-data {r.status}: {data.get('message') if isinstance(data, dict) else data}")
            return data

    async def competition_matches(self, code: str, date_from: str, date_to: str):
        data = await self._get(f"/competitions/{code}/matches", {"dateFrom": date_from, "dateTo": date_to})
        return data.get("matches", []), data.get("competition", {}) or {}

    async def match(self, match_id: int):
        return await self._get(f"/matches/{match_id}")


FD_STATUS = {
    "SCHEDULED": "NS", "TIMED": "NS", "IN_PLAY": "1H", "PAUSED": "HT", "FINISHED": "FT",
    "POSTPONED": "PST", "SUSPENDED": "SUSP", "CANCELLED": "CANC", "AWARDED": "AWD",
}


def parse_fd_match(it: dict, comp: dict, league_id: int) -> dict:
    ts = int(datetime.fromisoformat(it["utcDate"].replace("Z", "+00:00")).timestamp())
    c = it.get("competition") or comp or {}
    start = ((it.get("season") or {}).get("startDate") or "")[:4]
    ht, at = it.get("homeTeam") or {}, it.get("awayTeam") or {}
    ft = (it.get("score") or {}).get("fullTime") or {}
    return {
        "af_id": None,
        "fd_id": it["id"],
        "league_id": league_id,
        "league_name": c.get("name"),
        "league_logo": c.get("emblem"),
        "season": int(start) if start.isdigit() else datetime.utcfromtimestamp(ts).year,
        "round": f"Rodada {it['matchday']}" if it.get("matchday") else None,
        "home": ht.get("shortName") or ht.get("name"),
        "home_logo": ht.get("crest"),
        "away": at.get("shortName") or at.get("name"),
        "away_logo": at.get("crest"),
        "venue": it.get("venue"),
        "city": None,
        "kickoff": ts,
        "status": FD_STATUS.get(it.get("status"), "NS"),
        "elapsed": None,
        "home_goals": ft.get("home"),
        "away_goals": ft.get("away"),
        "detail": None,
    }