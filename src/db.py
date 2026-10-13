import json
import os

import aiosqlite

from logic import DEAD, FINISHED

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config(
  guild_id INTEGER PRIMARY KEY, partidas_ch INTEGER, resultados_ch INTEGER,
  ranking_ch INTEGER, ranking_msg_id INTEGER, leagues TEXT, alert_leagues TEXT, alert_role INTEGER);
CREATE TABLE IF NOT EXISTS matches(
  fixture_id INTEGER PRIMARY KEY, league_id INTEGER, league_name TEXT, league_logo TEXT,
  season INTEGER, round TEXT, home TEXT, home_logo TEXT, away TEXT, away_logo TEXT,
  venue TEXT, city TEXT, kickoff INTEGER, status TEXT, home_goals INTEGER, away_goals INTEGER,
  detail TEXT, finalized INTEGER DEFAULT 0, af_id INTEGER, fd_id INTEGER, elapsed INTEGER);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS partida_msgs(
  guild_id INTEGER, league_id INTEGER, channel_id INTEGER, message_id INTEGER PRIMARY KEY, deleted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS posts(
  guild_id INTEGER, fixture_id INTEGER, kind TEXT, channel_id INTEGER, message_id INTEGER,
  PRIMARY KEY(guild_id, fixture_id, kind));
CREATE TABLE IF NOT EXISTS predictions(
  guild_id INTEGER, fixture_id INTEGER, user_id INTEGER, home INTEGER, away INTEGER,
  points INTEGER, PRIMARY KEY(guild_id, fixture_id, user_id));
"""

MATCH_COLS = [
    "fixture_id", "league_id", "league_name", "league_logo", "season", "round", "home",
    "home_logo", "away", "away_logo", "venue", "city", "kickoff", "status", "home_goals",
    "away_goals", "af_id", "fd_id", "elapsed",
]


def _in(values):
    return ",".join("?" for _ in values)


class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        cols = {r["name"] for r in await self._all("PRAGMA table_info(matches)")}
        gcols = {r["name"] for r in await self._all("PRAGMA table_info(guild_config)")}
        for c, t in (("alert_leagues", "TEXT"), ("alert_role", "INTEGER")):
            if c not in gcols:
                await self.conn.execute(f"ALTER TABLE guild_config ADD COLUMN {c} {t}")
        for c in ("af_id", "fd_id", "elapsed"):
            if c not in cols:
                await self.conn.execute(f"ALTER TABLE matches ADD COLUMN {c} INTEGER")
        await self.conn.execute(
            "UPDATE matches SET af_id=fixture_id WHERE af_id IS NULL AND fd_id IS NULL AND fixture_id<1000000000"
        )
        await self.conn.commit()

    async def _all(self, sql, args=()):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchall()

    async def _one(self, sql, args=()):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchone()

    async def _run(self, sql, args=()):
        await self.conn.execute(sql, args)
        await self.conn.commit()

    async def get_meta(self, key):
        r = await self._one("SELECT value FROM meta WHERE key=?", (key,))
        return r["value"] if r else None

    async def set_meta(self, key, value):
        await self._run("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, value))

    # ---------- servidores ----------
    async def get_guild(self, guild_id):
        return await self._one("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))

    async def all_guilds(self):
        return await self._all("SELECT * FROM guild_config")

    async def set_channels(self, guild_id, partidas, resultados, ranking):
        await self._run(
            """INSERT INTO guild_config(guild_id, partidas_ch, resultados_ch, ranking_ch)
               VALUES(?,?,?,?) ON CONFLICT(guild_id) DO UPDATE SET
               partidas_ch=excluded.partidas_ch, resultados_ch=excluded.resultados_ch,
               ranking_ch=excluded.ranking_ch, ranking_msg_id=NULL""",
            (guild_id, partidas, resultados, ranking),
        )

    async def set_leagues(self, guild_id, ids):
        await self._run("UPDATE guild_config SET leagues=? WHERE guild_id=?", (json.dumps(ids), guild_id))

    async def set_alert_leagues(self, guild_id, ids):
        await self._run("UPDATE guild_config SET alert_leagues=? WHERE guild_id=?", (json.dumps(ids), guild_id))

    async def set_alert_role(self, guild_id, role_id):
        await self._run("UPDATE guild_config SET alert_role=? WHERE guild_id=?", (role_id, guild_id))

    async def set_ranking_msg(self, guild_id, msg_id):
        await self._run("UPDATE guild_config SET ranking_msg_id=? WHERE guild_id=?", (msg_id, guild_id))

    # ---------- jogos ----------
    async def insert_match(self, m: dict, finalized: int = 0):
        cols = ["fixture_id"] + MATCH_COLS[1:]
        await self._run(
            f"INSERT OR REPLACE INTO matches({','.join(cols)}, detail, finalized) VALUES({_in(cols)},?,?)",
            [m.get(c) for c in cols] + [m.get("detail"), finalized],
        )

    UPDATABLE = {"kickoff", "status", "venue", "city", "round", "league_logo", "home_logo", "away_logo",
                 "af_id", "fd_id", "finalized", "home_logo", "away_logo"}

    async def update_fields(self, fixture_id, **fields):
        if not fields:
            return
        assert set(fields) <= self.UPDATABLE
        sets = ",".join(f"{k}=?" for k in fields)
        await self._run(f"UPDATE matches SET {sets} WHERE fixture_id=?", (*fields.values(), fixture_id))

    async def get_by_af(self, af_id):
        return await self._one("SELECT * FROM matches WHERE af_id=?", (af_id,))

    async def get_by_fd(self, fd_id):
        return await self._one("SELECT * FROM matches WHERE fd_id=?", (fd_id,))

    async def candidates(self, league_id, kickoff, missing_col, window=3600):
        assert missing_col in ("af_id", "fd_id")
        return await self._all(
            f"""SELECT * FROM matches WHERE league_id=? AND ABS(kickoff-?)<=? AND {missing_col} IS NULL
                AND finalized=0""",
            (league_id, kickoff, window),
        )

    async def update_match_result(self, m: dict):
        """Resultado vindo da API-Football (com eventos/estatísticas)."""
        await self._run(
            """UPDATE matches SET status=?, home_goals=?, away_goals=?, elapsed=?, detail=COALESCE(?, detail),
               finalized=CASE WHEN ? THEN 1 ELSE finalized END WHERE af_id=?""",
            (m["status"], m["home_goals"], m["away_goals"], m.get("elapsed"), m["detail"], m["status"] in DEAD, m["af_id"]),
        )

    async def set_result(self, fixture_id, status, hg, ag):
        """Resultado de reserva (football-data.org), sem súmula."""
        await self._run(
            "UPDATE matches SET status=?, home_goals=?, away_goals=? WHERE fixture_id=?",
            (status, hg, ag, fixture_id),
        )

    async def mark_finalized(self, fid):
        await self._run("UPDATE matches SET finalized=1 WHERE fixture_id=?", (fid,))

    async def get_match(self, fid):
        return await self._one("SELECT * FROM matches WHERE fixture_id=?", (fid,))

    async def matches_to_post(self, guild_id, league_ids, now):
        if not league_ids:
            return []
        return await self._all(
            f"""SELECT m.* FROM matches m WHERE m.status IN ('NS','TBD') AND m.kickoff>?
                AND m.league_id IN ({_in(league_ids)})
                AND NOT EXISTS(SELECT 1 FROM posts p WHERE p.guild_id=? AND p.fixture_id=m.fixture_id AND p.kind='partida')
                ORDER BY m.kickoff""",
            (now, *league_ids, guild_id),
        )

    async def tracking(self, now):
        """Jogos já iniciados e ainda não encerrados (candidatos a consulta ao vivo)."""
        stop = tuple(FINISHED | DEAD | {"PST"})
        return await self._all(
            f"""SELECT * FROM matches WHERE finalized=0 AND af_id IS NOT NULL AND status NOT IN ({_in(stop)})
                AND kickoff<=? AND kickoff>?""",
            (*stop, now, now - 36 * 3600),
        )

    async def unmapped_pending(self, now):
        stop = tuple(FINISHED | DEAD | {"PST"})
        return await self._all(
            f"""SELECT * FROM matches WHERE finalized=0 AND af_id IS NULL AND fd_id IS NOT NULL
                AND status NOT IN ({_in(stop)}) AND kickoff<? AND kickoff>?""",
            (*stop, now - 3 * 3600, now - 36 * 3600),
        )

    async def finished_unfinalized(self):
        fin = tuple(FINISHED)
        return await self._all(
            f"SELECT * FROM matches WHERE finalized=0 AND status IN ({_in(fin)})", fin
        )

    # ---------- mensagens postadas ----------
    async def add_post(self, guild_id, fid, kind, channel_id, message_id):
        await self._run(
            "INSERT OR REPLACE INTO posts VALUES(?,?,?,?,?)", (guild_id, fid, kind, channel_id, message_id)
        )

    async def get_post(self, guild_id, fid, kind):
        return await self._one(
            "SELECT * FROM posts WHERE guild_id=? AND fixture_id=? AND kind=?", (guild_id, fid, kind)
        )

    async def add_container(self, guild_id, league_id, channel_id, message_id):
        await self._run("INSERT OR REPLACE INTO partida_msgs VALUES(?,?,?,?,0)", (guild_id, league_id, channel_id, message_id))

    async def active_containers(self, guild_id, league_id):
        return await self._all(
            "SELECT * FROM partida_msgs WHERE guild_id=? AND league_id=? AND deleted=0 ORDER BY message_id DESC",
            (guild_id, league_id),
        )

    async def get_container(self, message_id):
        return await self._one("SELECT * FROM partida_msgs WHERE message_id=? AND deleted=0", (message_id,))

    async def mark_container_deleted(self, message_id):
        await self._run("UPDATE partida_msgs SET deleted=1 WHERE message_id=?", (message_id,))

    async def fixtures_in_message(self, guild_id, message_id):
        return await self._all(
            """SELECT m.* FROM posts p JOIN matches m ON m.fixture_id=p.fixture_id
               WHERE p.guild_id=? AND p.kind='partida' AND p.message_id=? ORDER BY m.kickoff""",
            (guild_id, message_id),
        )

    async def upcoming_partida_posts(self, guild_id, now):
        return await self._all(
            """SELECT p.* FROM posts p JOIN matches m ON m.fixture_id=p.fixture_id
               WHERE p.guild_id=? AND p.kind='partida' AND m.status IN ('NS','TBD') AND m.kickoff>?""",
            (guild_id, now),
        )

    async def active_containers_all(self, guild_id):
        return await self._all("SELECT * FROM partida_msgs WHERE guild_id=? AND deleted=0", (guild_id,))

    async def reset_partidas(self, guild_id, now):
        """Esquece que os jogos futuros foram postados (jogos ao vivo/encerrados ficam como estão)."""
        await self.conn.execute(
            """DELETE FROM posts WHERE guild_id=? AND kind='partida' AND fixture_id IN
               (SELECT fixture_id FROM matches WHERE status IN ('NS','TBD') AND kickoff>?)""",
            (guild_id, now),
        )
        await self.conn.execute("UPDATE partida_msgs SET deleted=1 WHERE guild_id=?", (guild_id,))
        await self.conn.commit()

    async def posts_for(self, fid, kind):
        return await self._all("SELECT * FROM posts WHERE fixture_id=? AND kind=?", (fid, kind))

    # ---------- palpites ----------
    async def save_prediction(self, guild_id, fid, user_id, home, away):
        await self._run(
            """INSERT INTO predictions(guild_id, fixture_id, user_id, home, away) VALUES(?,?,?,?,?)
               ON CONFLICT(guild_id, fixture_id, user_id) DO UPDATE SET home=excluded.home, away=excluded.away""",
            (guild_id, fid, user_id, home, away),
        )

    async def get_prediction(self, guild_id, fid, user_id):
        return await self._one(
            "SELECT * FROM predictions WHERE guild_id=? AND fixture_id=? AND user_id=?", (guild_id, fid, user_id)
        )

    async def predictions_for(self, fid):
        return await self._all("SELECT * FROM predictions WHERE fixture_id=?", (fid,))

    async def set_points(self, guild_id, fid, user_id, pts):
        await self._run(
            "UPDATE predictions SET points=? WHERE guild_id=? AND fixture_id=? AND user_id=?",
            (pts, guild_id, fid, user_id),
        )

    async def ranking(self, guild_id, limit=15):
        return await self._all(
            """SELECT user_id, SUM(points) pts, SUM(points>=3) exact, SUM(points=1) hits, COUNT(*) n
               FROM predictions WHERE guild_id=? AND points IS NOT NULL
               GROUP BY user_id ORDER BY pts DESC, exact DESC, hits DESC LIMIT ?""",
            (guild_id, limit),
        )

    async def user_predictions(self, guild_id, user_id, limit=10):
        return await self._all(
            """SELECT p.home ph, p.away pa, p.points, m.* FROM predictions p
               JOIN matches m ON m.fixture_id=p.fixture_id
               WHERE p.guild_id=? AND p.user_id=? ORDER BY m.kickoff DESC LIMIT ?""",
            (guild_id, user_id, limit),
        )