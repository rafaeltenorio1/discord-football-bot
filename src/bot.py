import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands, tasks

import config
import embeds
import merge
from src.api import FD_STATUS, ApiError, ApiFootball, FootballData, parse_fd_match, parse_fixture
from db import DB
from logic import DEAD, FINISHED, LIVE, live_interval, score_prediction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


# ======================= Botões e modal =======================
class PalpiteModal(discord.ui.Modal):
    def __init__(self, m, current):
        super().__init__(title=f"{m['home']} x {m['away']}"[:45])
        self.fid = m["fixture_id"]
        self.home_in = discord.ui.TextInput(
            label=f"Gols: {m['home']}"[:45], min_length=1, max_length=2,
            default=str(current["home"]) if current else None,
        )
        self.away_in = discord.ui.TextInput(
            label=f"Gols: {m['away']}"[:45], min_length=1, max_length=2,
            default=str(current["away"]) if current else None,
        )
        self.add_item(self.home_in)
        self.add_item(self.away_in)

    async def on_submit(self, interaction: discord.Interaction):
        db: DB = interaction.client.db
        m = await db.get_match(self.fid)
        if time.time() >= m["kickoff"]:
            return await interaction.response.send_message("⏱️ Os palpites desse jogo já foram encerrados.", ephemeral=True)
        h, a = self.home_in.value.strip(), self.away_in.value.strip()
        if not (h.isdigit() and a.isdigit()):
            return await interaction.response.send_message("Use apenas números inteiros (ex.: 2 e 1).", ephemeral=True)
        await db.save_prediction(interaction.guild_id, self.fid, interaction.user.id, int(h), int(a))
        await interaction.response.send_message(
            f"✅ Palpite salvo: **{m['home']} {int(h)} X {int(a)} {m['away']}**\nVocê pode alterar até o início do jogo.",
            ephemeral=True,
        )


class PalpiteButton(discord.ui.DynamicItem[discord.ui.Button], template=r"palpite:(?P<id>\d+)"):
    def __init__(self, fid: int):
        super().__init__(discord.ui.Button(label="Palpitar", emoji="🎯", style=discord.ButtonStyle.primary, custom_id=f"palpite:{fid}"))
        self.fid = fid

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        db: DB = interaction.client.db
        m = await db.get_match(self.fid)
        if m is None or time.time() >= m["kickoff"]:
            return await interaction.response.send_message("⏱️ Os palpites desse jogo já foram encerrados.", ephemeral=True)
        cur = await db.get_prediction(interaction.guild_id, self.fid, interaction.user.id)
        await interaction.response.send_modal(PalpiteModal(m, cur))


class SumulaButton(discord.ui.DynamicItem[discord.ui.Button], template=r"sumula:(?P<id>\d+)"):
    def __init__(self, fid: int):
        super().__init__(discord.ui.Button(label="Súmula", emoji="📋", style=discord.ButtonStyle.primary, custom_id=f"sumula:{fid}"))
        self.fid = fid

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        m = await interaction.client.db.get_match(self.fid)
        if not m or not m["detail"]:
            return await interaction.response.send_message("Súmula indisponível para esse jogo.", ephemeral=True)
        await interaction.response.send_message(embed=embeds.sumula_embed(m), ephemeral=True)


class StatsButton(discord.ui.DynamicItem[discord.ui.Button], template=r"stats:(?P<id>\d+)"):
    def __init__(self, fid: int):
        super().__init__(discord.ui.Button(label="Estatísticas", emoji="📊", style=discord.ButtonStyle.primary, custom_id=f"stats:{fid}"))
        self.fid = fid

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        m = await interaction.client.db.get_match(self.fid)
        e = embeds.stats_embed(m) if m else None
        if e is None:
            return await interaction.response.send_message("Estatísticas indisponíveis para esse jogo.", ephemeral=True)
        await interaction.response.send_message(embed=e, ephemeral=True)


class PalpiteSelectView(discord.ui.View):
    """Menu 'Escolha um jogo para palpitar' que fica embaixo de cada container de competição."""

    def __init__(self, rows=None):
        super().__init__(timeout=None)
        if rows:
            tz = ZoneInfo(config.TIMEZONE)
            self.pick.options = [
                discord.SelectOption(
                    label=f"{m['home']} X {m['away']}"[:100],
                    description=datetime.fromtimestamp(m["kickoff"], tz).strftime("%d/%m às %H:%M"),
                    value=str(m["fixture_id"]),
                )
                for m in sorted(rows, key=lambda r: r["kickoff"])[:25]
            ]

    @discord.ui.select(
        custom_id="palpite_select", placeholder="🎯 Escolha um jogo para palpitar",
        options=[discord.SelectOption(label="jogo", value="0")],
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.Select):
        db: DB = interaction.client.db
        m = await db.get_match(int(select.values[0]))
        if m is None or time.time() >= m["kickoff"]:
            return await interaction.response.send_message("⏱️ Os palpites desse jogo já foram encerrados.", ephemeral=True)
        cur = await db.get_prediction(interaction.guild_id, m["fixture_id"], interaction.user.id)
        await interaction.response.send_modal(PalpiteModal(m, cur))


def partida_view(fid):
    v = discord.ui.View(timeout=None)
    v.add_item(PalpiteButton(fid))
    return v


def resultado_view(fid):
    v = discord.ui.View(timeout=None)
    v.add_item(SumulaButton(fid))
    v.add_item(StatsButton(fid))
    return v


# ======================= Bot =======================
class GingaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.db = DB(config.DB_PATH)
        self.api: ApiFootball | None = None
        self.fd: FootballData | None = None
        self.session: aiohttp.ClientSession | None = None
        self.sync_lock = asyncio.Lock()
        self.last_track = 0
        self.detail_done: set[int] = set()
        self.crest_cache: dict[str, str] = {}
        self.emoji_failed: dict[str, float] = {}  # nome -> não tentar de novo antes deste horário
        self.net_down_until = 0.0
        self.emoji_ok = True

    async def setup_hook(self):
        await self.db.connect()
        self.session = aiohttp.ClientSession()
        self.api = ApiFootball(config.API_FOOTBALL_KEY, self.session, config.TIMEZONE)
        if config.FOOTBALL_DATA_TOKEN:
            self.fd = FootballData(config.FOOTBALL_DATA_TOKEN, self.session)
        self.add_dynamic_items(PalpiteButton, SumulaButton, StatsButton)
        self.add_view(PalpiteSelectView())
        register_commands(self)
        if config.DEV_GUILD_ID:
            g = discord.Object(int(config.DEV_GUILD_ID))
            self.tree.copy_global_to(guild=g)
            await self.tree.sync(guild=g)
        else:
            await self.tree.sync()
        if config.PORT:
            await self.start_health_server()
        await self.load_emojis()
        self.sync_loop.start()
        self.results_loop.start()

    async def start_health_server(self):
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text="ok"))
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", int(config.PORT)).start()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    # ---------- utilidades ----------
    async def channel(self, cid):
        if not cid:
            return None
        ch = self.get_channel(cid)
        if ch is None:
            try:
                ch = await self.fetch_channel(cid)
            except discord.HTTPException:
                return None
        return ch

    @staticmethod
    def guild_leagues(g) -> list[int]:
        return json.loads(g["leagues"]) if g["leagues"] else list(config.LEAGUES)

    # ---------- canal #partidas ----------
    async def merge(self, m: dict, src: str):
        """Junta um jogo vindo de uma das APIs ao banco. Retorna (fixture_id, horario_mudou)."""
        key = "af_id" if src == "af" else "fd_id"
        getter = self.db.get_by_af if src == "af" else self.db.get_by_fd
        row = await getter(m[key])
        if row is None:  # tenta casar com o mesmo jogo vindo da outra API
            row = merge.pick(m, await self.db.candidates(m["league_id"], m["kickoff"], key))
            if row:
                await self.db.update_fields(row["fixture_id"], **{key: m[key]})
                row = await self.db.get_match(row["fixture_id"])
        if row is None:
            fid = m[key] if src == "af" else config.FD_OFFSET + m[key]
            await self.db.insert_match(dict(m, fixture_id=fid))
            return fid, False

        fields = {c: m[c] for c in ("venue", "city", "round", "league_logo", "home_logo", "away_logo") if not row[c] and m.get(c)}
        if src == "af":  # prefere o PNG da API-Football (emoji do Discord não aceita SVG)
            for c in ("home_logo", "away_logo"):
                if m.get(c) and (not row[c] or str(row[c]).lower().endswith(".svg")):
                    fields[c] = m[c]
        changed = False
        if row["status"] not in FINISHED:
            if src == "af" and m["status"] not in FINISHED:
                # API-Football manda no horário/status; o resultado final vem do results_loop (com súmula)
                fields.update(kickoff=m["kickoff"], status=m["status"])
                if m["status"] in DEAD:
                    fields["finalized"] = 1
                elif m["status"] in ("NS", "TBD"):
                    fields["finalized"] = 0
                changed = row["kickoff"] != m["kickoff"]
            elif src == "fd" and row["af_id"] is None and row["status"] in ("NS", "TBD", "PST"):
                if m["status"] in ("NS", "PST", "CANC"):
                    fields["status"] = m["status"]
                    if m["status"] == "NS":
                        fields.update(kickoff=m["kickoff"], finalized=0)
                        changed = row["kickoff"] != m["kickoff"]
                    if m["status"] == "CANC":
                        fields["finalized"] = 1
        await self.db.update_fields(row["fixture_id"], **fields)
        return row["fixture_id"], changed

    async def sync_upcoming(self, min_age: int = 0) -> dict:
        """Busca jogos nas APIs (se a última busca for mais velha que min_age segundos)
        e posta no Discord o que ainda não foi postado."""
        async with self.sync_lock:
            stats = {"found": 0, "posted": 0, "skipped": False, "error": None}
            last = int(await self.db.get_meta("last_sync") or 0)
            if time.time() - last < min_age:
                stats["skipped"] = True
            else:
                seen, changed = set(), []

                def note(res):
                    seen.add(res[0])
                    if res[1]:
                        changed.append(res[0])

                # 1) football-data.org: a rodada completa (sem custo da cota da API-Football)
                if self.fd:
                    d0 = datetime.now(timezone.utc).date()
                    d1 = d0 + timedelta(days=config.FD_DAYS_AHEAD)
                    for code, league_id in config.FD_COMPETITIONS.items():
                        try:
                            items, comp = await self.fd.competition_matches(code, d0.isoformat(), d1.isoformat())
                        except ApiError as e:
                            log.error("football-data recusou (%s): %s", code, e)
                            stats["error"] = f"football-data: {e}"
                            continue
                        for it in items:
                            m = parse_fd_match(it, comp, league_id)
                            if m["home"] and m["away"]:
                                note(await self.merge(m, "fd"))
                        await asyncio.sleep(1)  # limite de 10 req/min
                # 2) API-Football: ontem/hoje/amanhã (venue, escudos, ID para súmula e estatísticas)
                if self.api.remaining is not None and self.api.remaining < 10:
                    stats["error"] = stats["error"] or "restam poucas requisições da API-Football hoje; busca dela adiada"
                else:
                    today = datetime.now(ZoneInfo(config.TIMEZONE)).date()
                    for i in range(config.DAYS_AHEAD + 1):
                        d = today + timedelta(days=i)
                        try:
                            items = await self.api.fixtures_by_date(d.isoformat())
                        except ApiError as e:
                            log.error("API-Football recusou: %s", e)
                            stats["error"] = f"API-Football: {e}"
                            break
                        for it in items:
                            if it["league"]["id"] in config.LEAGUES:
                                note(await self.merge(parse_fixture(it), "af"))
                stats["found"] = len(seen)
                if not stats["error"]:
                    await self.db.set_meta("last_sync", str(int(time.time())))
                for fid in changed:
                    await self.refresh_partida_posts(fid)
            for g in await self.db.all_guilds():
                stats["posted"] += await self.post_new_partidas(g)
            return stats

    # ---------- escudos como emojis ----------
    async def load_emojis(self):
        try:
            self.crest_cache = {e.name: str(e) for e in await self.fetch_application_emojis()}
        except Exception as e:
            log.warning("Emojis de aplicação indisponíveis (%s); escudos desativados.", e)
            self.emoji_ok = False

    async def crest(self, url) -> str:
        """Devolve o emoji do escudo (criando-o no Discord na primeira vez) ou '' se não der."""
        if not url or not self.emoji_ok or url.lower().split("?")[0].endswith(".svg"):
            return ""
        name = "t" + hashlib.md5(url.encode()).hexdigest()[:12]
        if name in self.crest_cache:
            return self.crest_cache[name]
        now = time.time()
        if now < self.net_down_until or self.emoji_failed.get(name, 0) > now:
            return ""
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    raise ValueError(f"download {r.status}")
                data = await r.read()
            if len(data) > 256 * 1024:
                raise ValueError("imagem maior que 256 KB")
            self.crest_cache[name] = str(await self.create_application_emoji(name=name, image=data))
            return self.crest_cache[name]
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
            # sem internet/DNS: pausa todos os downloads de escudo por 10 min e tenta de novo depois
            self.net_down_until = now + 600
            log.warning("Sem acesso a %s (%s). Escudos adiados por 10 min.", url.split('/')[2], e)
            return ""
        except Exception as e:
            log.warning("Sem emoji para %s: %s", url, e)
            self.emoji_failed[name] = now + 6 * 3600
            return ""

    async def make_container(self, rows):
        emo = {}
        for m in rows:
            for u in (m["home_logo"], m["away_logo"]):
                if u and u not in emo:
                    emo[u] = await self.crest(u)
        return embeds.container_embed(rows, emo), PalpiteSelectView(rows)

    async def fit(self, base, pending):
        """Quantos jogos de `pending` cabem no container (máx. 25 opções e ~3800 caracteres)."""
        take = []
        for m in pending:
            trial = base + take + [m]
            emb, _ = await self.make_container(trial)
            if len(trial) <= 25 and len(emb.description) <= 3800:
                take.append(m)
            else:
                break
        return take

    @staticmethod
    def upcoming(rows):
        return [r for r in rows if r["status"] in ("NS", "TBD")]

    # ---------- canal #partidas: um container por competição ----------
    async def post_new_partidas(self, g) -> int:
        ch = await self.channel(g["partidas_ch"])
        if ch is None:
            return 0
        new = await self.db.matches_to_post(g["guild_id"], self.guild_leagues(g), int(time.time()))
        by_league: dict[int, list] = {}
        for m in new:
            by_league.setdefault(m["league_id"], []).append(m)
        n = 0
        for league_id in config.LEAGUES:  # ordem de prioridade definida em config.py
            if league_id in by_league:
                try:
                    n += await self.add_to_containers(g, ch, league_id, by_league[league_id])
                except discord.HTTPException as e:
                    log.error("Falha ao postar partidas: %s", e)
        return n

    async def add_to_containers(self, g, ch, league_id, pending) -> int:
        gid, n = g["guild_id"], 0
        pending = list(pending)
        for c in (await self.db.active_containers(gid, league_id))[:1]:
            base = self.upcoming(await self.db.fixtures_in_message(gid, c["message_id"]))
            take = await self.fit(base, pending)
            if not take:
                break
            try:
                msg = await (await self.channel(c["channel_id"])).fetch_message(c["message_id"])
            except (discord.NotFound, AttributeError):
                await self.db.mark_container_deleted(c["message_id"])
                break
            emb, view = await self.make_container(base + take)
            await msg.edit(embed=emb, view=view)
            for m in take:
                await self.db.add_post(gid, m["fixture_id"], "partida", ch.id, msg.id)
            pending, n = pending[len(take):], n + len(take)
        while pending:
            take = await self.fit([], pending) or [pending[0]]
            emb, view = await self.make_container(take)
            msg = await ch.send(embed=emb, view=view)
            await self.db.add_container(gid, league_id, ch.id, msg.id)
            for m in take:
                await self.db.add_post(gid, m["fixture_id"], "partida", ch.id, msg.id)
            pending, n = pending[len(take):], n + len(take)
            await asyncio.sleep(1)
        return n

    async def repost_partidas(self, g, refresh: bool = False) -> dict:
        """Apaga os containers atuais (se ainda existirem) e posta de novo todos os jogos futuros."""
        gid, now = g["guild_id"], int(time.time())
        async with self.sync_lock:
            targets = {(r["channel_id"], r["message_id"]) for r in await self.db.upcoming_partida_posts(gid, now)}
            targets |= {(c["channel_id"], c["message_id"]) for c in await self.db.active_containers_all(gid)}
            for ch_id, mid in targets:
                ch = await self.channel(ch_id)
                if ch is None:
                    continue
                try:
                    await (await ch.fetch_message(mid)).delete()
                except (discord.NotFound, discord.Forbidden):
                    pass  # já apagada (ou sem permissão): segue
                except discord.HTTPException as e:
                    log.error("Falha ao apagar mensagem antiga: %s", e)
            await self.db.reset_partidas(gid, now)
        if refresh:
            stats = await self.sync_upcoming(min_age=15 * 60)  # também posta o que está no banco
            return {"posted": stats["posted"], "error": stats["error"], "skipped": stats["skipped"]}
        async with self.sync_lock:
            return {"posted": await self.post_new_partidas(g), "error": None, "skipped": False}

    async def rebuild_container(self, guild_id, message_id):
        """Reconstrói um container (jogo remarcado/encerrado). Apaga a mensagem se não sobrar jogo."""
        c = await self.db.get_container(message_id)
        if not c:
            return False
        ch = await self.channel(c["channel_id"])
        if ch is None:
            return True
        rows = self.upcoming(await self.db.fixtures_in_message(guild_id, message_id))
        try:
            msg = await ch.fetch_message(message_id)
            if not rows:
                await msg.delete()
                await self.db.mark_container_deleted(message_id)
            else:
                emb, view = await self.make_container(rows)
                await msg.edit(embed=emb, view=view)
        except discord.NotFound:
            await self.db.mark_container_deleted(message_id)
        except discord.HTTPException as e:
            log.error("Falha ao atualizar container: %s", e)
        return True

    async def refresh_partida_posts(self, fid):
        m = await self.db.get_match(fid)
        for p in await self.db.posts_for(fid, "partida"):
            if await self.rebuild_container(p["guild_id"], p["message_id"]):
                continue
            ch = await self.channel(p["channel_id"])  # mensagem antiga (um jogo por mensagem)
            if ch is None:
                continue
            try:
                msg = await ch.fetch_message(p["message_id"])
                await msg.edit(embed=embeds.partida_embed(m))
            except discord.HTTPException:
                pass

    @tasks.loop(hours=3)
    async def sync_loop(self):
        try:
            await self.sync_upcoming(min_age=170 * 60)
        except Exception:
            log.exception("erro no sync")

    # ---------- canais #resultados e #ranking ----------
    async def emo_for(self, m):
        return {u: await self.crest(u) for u in (m["home_logo"], m["away_logo"]) if u}

    def local_date(self, ts: int) -> str:
        return datetime.fromtimestamp(ts, ZoneInfo(config.TIMEZONE)).date().isoformat()

    def quota_ok(self, minimum: int) -> bool:
        return self.api.remaining is None or self.api.remaining >= minimum

    async def poll_live(self, rows):
        """Atualiza placar/status dos jogos em andamento. Uma consulta por data cobre todos os jogos do dia."""
        by_date: dict[str, dict] = {}
        for r in rows:
            by_date.setdefault(self.local_date(r["kickoff"]), {})[r["af_id"]] = r
        for d, wanted in by_date.items():
            try:
                items = await self.api.fixtures_by_date(d)
            except ApiError as e:
                log.error("API-Football recusou: %s", e)
                continue
            for it in items:
                old = wanted.get(it["fixture"]["id"])
                if old is None:
                    continue
                new = parse_fixture(it)
                goals_changed = (old["home_goals"], old["away_goals"]) != (new["home_goals"], new["away_goals"])
                if (goals_changed and new["status"] in LIVE and not new["detail"] and config.LIVE_SCORERS
                        and (new["home_goals"] or 0) + (new["away_goals"] or 0) > 0 and self.quota_ok(30)):
                    try:  # busca quem fez o gol
                        det = await self.api.fixture_detail(new["af_id"])
                        if det:
                            new = parse_fixture(det)
                    except ApiError as e:
                        log.warning("Sem detalhes do gol: %s", e)
                await self.db.update_match_result(new)
                if new["status"] in LIVE:
                    changed = old["status"] != new["status"] or goals_changed or old["elapsed"] != new["elapsed"]
                    await self.live_update(old["fixture_id"], force=changed)
                    if goals_changed:
                        await self.send_goal_alert(old, new)

    async def ensure_detail(self, m):
        """Garante súmula/estatísticas de um jogo encerrado (1 requisição)."""
        # sempre busca a versão final (os dados guardados durante o jogo são parciais), uma vez por jogo
        if not m["af_id"] or m["fixture_id"] in self.detail_done or not self.quota_ok(2):
            return
        self.detail_done.add(m["fixture_id"])
        try:
            det = await self.api.fixture_detail(m["af_id"])
        except ApiError as e:
            log.error("API-Football recusou: %s", e)
            return
        if det:
            await self.db.update_match_result(parse_fixture(det))

    @staticmethod
    def alert_leagues(g) -> list[int]:
        return json.loads(g["alert_leagues"]) if g["alert_leagues"] is not None else list(config.LEAGUES)

    async def send_goal_alert(self, old, new):
        """Mensagem nova a cada gol (editar mensagem não gera notificação no Discord)."""
        if old["home_goals"] is None or old["away_goals"] is None:
            return  # primeira leitura do jogo: não alerta placar que já existia
        oh, oa = old["home_goals"], old["away_goals"]
        nh, na = new["home_goals"] or 0, new["away_goals"] or 0
        if nh + na == oh + oa:
            return
        m = await self.db.get_match(old["fixture_id"])
        minute = f" — {new['elapsed']}'" if new.get("elapsed") else ""
        score = f"{m['home']} **{nh}** X **{na}** {m['away']}"
        if nh + na > oh + oa:
            team = m["home"] if nh > oh and na == oa else m["away"] if na > oa and nh == oh else None
            head = f"⚽ **GOOOL do {team}!**" if team else "⚽ **GOOOL!**"
            lines = embeds.goal_lines(new["detail"])
            extra = f"\n{lines[-1]}" if lines and len(lines) == nh + na else ""
            body = f"{head} {score}{minute}{extra}"
        else:
            body = f"❌ **Gol anulado!** {score}{minute}"
        for g in await self.db.all_guilds():
            if m["league_id"] not in self.alert_leagues(g):
                continue
            if not await self.db.get_post(g["guild_id"], m["fixture_id"], "partida"):
                continue
            ch = await self.channel(g["resultados_ch"])
            if ch is None:
                continue
            role = g["alert_role"]
            try:
                await ch.send(
                    (f"<@&{role}> " if role else "") + body,
                    allowed_mentions=discord.AllowedMentions(roles=[discord.Object(id=role)] if role else False),
                    delete_after=config.ALERT_DELETE_MINUTES * 60 or None,
                )
            except discord.HTTPException as e:
                log.error("Falha ao enviar alerta de gol: %s", e)

    async def live_update(self, fid, force=True):
        """Posta (ou edita) a mensagem ao vivo no canal #resultados. Não gasta a API."""
        m = await self.db.get_match(fid)
        emb = embeds.live_embed(m, await self.emo_for(m))
        for g in await self.db.all_guilds():
            gid = g["guild_id"]
            part = await self.db.get_post(gid, fid, "partida")
            if not part:
                continue
            post = await self.db.get_post(gid, fid, "resultado")
            if post:
                if not force:
                    continue
                ch = await self.channel(post["channel_id"])
                try:
                    msg = await ch.fetch_message(post["message_id"])
                    await msg.edit(embed=emb)
                    continue
                except (discord.NotFound, AttributeError):
                    pass
                except discord.HTTPException as e:
                    log.error("Falha ao editar placar ao vivo: %s", e)
                    continue
            ch = await self.channel(g["resultados_ch"])
            if ch is None:
                continue
            try:
                msg = await ch.send(embed=emb)
                await self.db.add_post(gid, fid, "resultado", ch.id, msg.id)
            except discord.HTTPException as e:
                log.error("Falha ao postar placar ao vivo: %s", e)
                continue
            await self.rebuild_container(gid, part["message_id"])  # tira o jogo de #partidas

    async def fd_fallback(self, rows):
        """Resultado de reserva (sem súmula) para jogos que não casaram com a API-Football."""
        for r in rows:
            try:
                d = await self.fd.match(r["fd_id"])
            except ApiError as e:
                log.error("football-data recusou: %s", e)
                continue
            st = FD_STATUS.get(d.get("status"), "NS")
            ft = (d.get("score") or {}).get("fullTime") or {}
            if st == "FT" and ft.get("home") is not None:
                await self.db.set_result(r["fixture_id"], "FT", ft["home"], ft["away"])
            await asyncio.sleep(7)

    @tasks.loop(minutes=1)
    async def results_loop(self):
        try:
            now = int(time.time())
            rem = self.api.remaining
            interval = live_interval(rem, config.LIVE_INTERVAL_MINUTES)
            ids, old = [], []
            for r in await self.db.tracking(now):
                age = now - r["kickoff"]
                if age > 4 * 3600:
                    old.append(r)
                elif interval is not None and r["league_id"] in config.LIVE_LEAGUES:
                    ids.append(r)                               # ao vivo, desde o apito inicial
                elif age >= (95 if interval is not None else 100) * 60:
                    ids.append(r)                               # só o resultado final
            gap = (interval or 15) * 60
            if ids and (rem is None or rem >= 3) and now - self.last_track >= gap - 20:
                self.last_track = now
                await self.poll_live(ids)  # 1 requisição por data cobre todos os jogos do dia
            if old and (rem is None or rem >= 3) and now - int(await self.db.get_meta("last_old_poll") or 0) >= 3600:
                await self.db.set_meta("last_old_poll", str(now))
                await self.poll_live(old)
            if self.fd and now - int(await self.db.get_meta("last_fd_fallback") or 0) >= 3600:
                rows = await self.db.unmapped_pending(now)
                if rows:
                    await self.db.set_meta("last_fd_fallback", str(now))
                    await self.fd_fallback(rows)
            for m in await self.db.finished_unfinalized():
                await self.ensure_detail(m)
                await self.finalize_match(m["fixture_id"])
        except Exception:
            log.exception("erro ao buscar resultados")

    @sync_loop.before_loop
    @results_loop.before_loop
    async def _wait(self):
        await self.wait_until_ready()

    async def finalize_match(self, fid):
        m = await self.db.get_match(fid)
        if m["home_goals"] is None or m["away_goals"] is None:
            return
        by_guild: dict[int, list] = {}
        for p in await self.db.predictions_for(fid):
            pts = score_prediction(p["home"], p["away"], m["home_goals"], m["away_goals"])
            await self.db.set_points(p["guild_id"], fid, p["user_id"], pts)
            by_guild.setdefault(p["guild_id"], []).append((p["user_id"], p["home"], p["away"], pts))

        for g in await self.db.all_guilds():
            if not await self.db.get_post(g["guild_id"], fid, "partida"):
                continue  # só posta resultado do que foi anunciado nesse servidor
            emb = embeds.resultado_embed(m, await self.emo_for(m))
            done = False
            old = await self.db.get_post(g["guild_id"], fid, "resultado")
            if old:  # a mensagem ao vivo vira o resultado final
                ch = await self.channel(old["channel_id"])
                try:
                    msg = await ch.fetch_message(old["message_id"])
                    await msg.edit(embed=emb, view=resultado_view(fid))
                    done = True
                except (discord.NotFound, AttributeError):
                    pass
                except discord.HTTPException as e:
                    log.error("Falha ao editar resultado: %s", e)
                    done = True
            if not done:
                ch = await self.channel(g["resultados_ch"])
                if ch:
                    try:
                        msg = await ch.send(embed=emb, view=resultado_view(fid))
                        await self.db.add_post(g["guild_id"], fid, "resultado", ch.id, msg.id)
                    except discord.HTTPException as e:
                        log.error("Falha ao postar resultado: %s", e)
            post = await self.db.get_post(g["guild_id"], fid, "partida")
            await self.rebuild_container(g["guild_id"], post["message_id"])
            await self.post_points_summary(g, m, by_guild.get(g["guild_id"], []))
            await self.update_ranking(g)
        await self.db.mark_finalized(fid)

    async def post_points_summary(self, g, m, rows):
        ch = await self.channel(g["ranking_ch"])
        if ch is None or not rows:
            return
        rows.sort(key=lambda r: -r[3])
        lines = [f"<@{u}> palpitou **{h} X {a}** → **+{pts}**" for u, h, a, pts in rows]
        e = discord.Embed(
            title=f"{m['home']} {m['home_goals']} X {m['away_goals']} {m['away']}",
            description="\n".join(lines)[:4000],
            color=embeds.COLOR,
        )
        try:
            await ch.send(embed=e)
        except discord.HTTPException:
            pass

    async def update_ranking(self, g):
        ch = await self.channel(g["ranking_ch"])
        if ch is None:
            return
        e = embeds.ranking_embed(await self.db.ranking(g["guild_id"]))
        if g["ranking_msg_id"]:
            try:
                msg = await ch.fetch_message(g["ranking_msg_id"])
                await msg.edit(embed=e)
                return
            except discord.NotFound:
                pass
            except discord.HTTPException:
                return
        try:
            msg = await ch.send(embed=e)
            await self.db.set_ranking_msg(g["guild_id"], msg.id)
            try:
                await msg.pin()
            except discord.HTTPException:
                pass
        except discord.HTTPException as ex:
            log.error("Falha ao postar ranking: %s", ex)


# ======================= Comandos =======================
class LeagueSelect(discord.ui.Select):
    def __init__(self, bot, selected):
        opts = [discord.SelectOption(label=v["name"], value=str(k), default=k in selected) for k, v in config.LEAGUES.items()]
        super().__init__(placeholder="Escolha as competições", min_values=1, max_values=len(opts), options=opts)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        ids = [int(v) for v in self.values]
        await self.bot.db.set_leagues(interaction.guild_id, ids)
        names = ", ".join(config.LEAGUES[i]["name"] for i in ids)
        await interaction.response.edit_message(content=f"✅ Competições ativas: {names}", view=None)


class AlertSelect(discord.ui.Select):
    def __init__(self, bot, selected):
        opts = [discord.SelectOption(label=v["name"], value=str(k), default=k in selected) for k, v in config.LEAGUES.items()]
        super().__init__(placeholder="Competições com alerta de gol", min_values=0, max_values=len(opts), options=opts)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        ids = [int(v) for v in self.values]
        await self.bot.db.set_alert_leagues(interaction.guild_id, ids)
        txt = ", ".join(config.LEAGUES[i]["name"] for i in ids) if ids else "nenhuma (alertas desligados)"
        await interaction.response.edit_message(content=f"✅ Alertas de gol: {txt}", view=None)


async def _mention(bot, g) -> str:
    return f"<#{g['partidas_ch']}>"


def register_commands(bot: GingaBot):
    tree = bot.tree

    @tree.command(name="configurar", description="Define os canais do bot (somente admins)")
    @app_commands.describe(partidas="Canal dos próximos jogos", resultados="Canal dos resultados", ranking="Canal do ranking de palpites")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def configurar(i: discord.Interaction, partidas: discord.TextChannel, resultados: discord.TextChannel, ranking: discord.TextChannel):
        await bot.db.set_channels(i.guild_id, partidas.id, resultados.id, ranking.id)
        await i.response.send_message(
            f"✅ Configurado!\n• Partidas: {partidas.mention}\n• Resultados: {resultados.mention}\n• Ranking: {ranking.mention}\n"
            "Buscando os jogos agora...", ephemeral=True,
        )
        asyncio.create_task(bot.sync_upcoming(min_age=170 * 60))
        g = await bot.db.get_guild(i.guild_id)
        await bot.update_ranking(g)

    @tree.command(name="ligas", description="Escolhe quais competições o bot acompanha (somente admins)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def ligas(i: discord.Interaction):
        g = await bot.db.get_guild(i.guild_id)
        if not g:
            return await i.response.send_message("Use /configurar primeiro.", ephemeral=True)
        v = discord.ui.View(timeout=120)
        v.add_item(LeagueSelect(bot, bot.guild_leagues(g)))
        await i.response.send_message("Quais competições?", view=v, ephemeral=True)

    @tree.command(name="alertas", description="Notificação a cada gol, por competição (somente admins)")
    @app_commands.describe(cargo="Cargo a marcar em cada gol (opcional)", sem_cargo="Parar de marcar o cargo")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def alertas(i: discord.Interaction, cargo: discord.Role | None = None, sem_cargo: bool = False):
        g = await bot.db.get_guild(i.guild_id)
        if not g:
            return await i.response.send_message("Use /configurar primeiro.", ephemeral=True)
        if cargo:
            await bot.db.set_alert_role(i.guild_id, cargo.id)
        elif sem_cargo:
            await bot.db.set_alert_role(i.guild_id, None)
        g = await bot.db.get_guild(i.guild_id)
        role = f"<@&{g['alert_role']}>" if g["alert_role"] else "nenhum"
        v = discord.ui.View(timeout=180)
        v.add_item(AlertSelect(bot, bot.alert_leagues(g)))
        await i.response.send_message(
            f"🔔 Cargo marcado nos alertas: {role}\nMarque as competições que devem avisar a cada gol "
            "(desmarque todas para desligar):", view=v, ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @tree.command(name="repostar", description="Apaga e reposta todos os jogos futuros em #partidas (somente admins)")
    @app_commands.describe(atualizar="Buscar jogos novos nas APIs antes de postar (gasta requisições)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def repostar(i: discord.Interaction, atualizar: bool = False):
        g = await bot.db.get_guild(i.guild_id)
        if not g:
            return await i.response.send_message("Use /configurar primeiro.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        r = await bot.repost_partidas(g, atualizar)
        if r["posted"]:
            txt = f"✅ {r['posted']} jogos postados em {await _mention(bot, g)}, agrupados por competição."
        else:
            txt = ("Não há jogos futuros salvos para postar. Use `/repostar atualizar:True` para buscar nas APIs "
                   "(ou espere a próxima busca automática, a cada 3 horas).")
        if r["skipped"]:
            txt += "\nA busca nas APIs foi pulada porque a última foi há menos de 15 min."
        if r["error"]:
            txt += f"\n⚠️ {r['error']}"
        await i.followup.send(txt, ephemeral=True)

    @tree.command(name="sincronizar", description="Busca jogos novos agora (somente admins)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def sincronizar(i: discord.Interaction):
        await i.response.send_message("🔄 Sincronizando...", ephemeral=True)
        s = await bot.sync_upcoming(min_age=15 * 60)
        rem = f"\nRequisições restantes hoje: {bot.api.remaining}" if bot.api.remaining is not None else ""
        if s["error"]:
            txt = f"⚠️ {s['error']}"
        elif s["skipped"]:
            txt = f"⏳ Já busquei jogos há menos de 15 min (economizando a API). Novos posts: {s['posted']}."
        elif s["found"] == 0:
            txt = "✅ Busca feita, mas não há jogos das competições suportadas entre ontem e amanhã."
        else:
            txt = f"✅ {s['found']} jogos encontrados nas competições suportadas. Novos posts: {s['posted']}."
        await i.edit_original_response(content=txt + rem)

    @tree.command(name="preview", description="Posta jogos de exemplo nos canais para ver o visual (somente admins)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def preview(i: discord.Interaction):
        g = await bot.db.get_guild(i.guild_id)
        if not g:
            return await i.response.send_message("Use /configurar primeiro.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        now = int(time.time())
        base = dict(league_id=71, league_name="Serie A", league_logo=None, season=2026, round="Rodada 30",
                    home="Cruzeiro", home_logo=None, away="Fluminense", away_logo=None,
                    venue="Estádio Governador Magalhães Pinto", city="Belo Horizonte", af_id=None, fd_id=None)
        events = [
            {"time": {"elapsed": 12, "extra": None}, "team": {"name": "Cruzeiro"}, "player": {"name": "Jogador A"}, "assist": {"name": "Jogador B"}, "type": "Goal", "detail": "Normal Goal"},
            {"time": {"elapsed": 45, "extra": 2}, "team": {"name": "Fluminense"}, "player": {"name": "Jogador C"}, "assist": {"name": None}, "type": "Card", "detail": "Yellow Card"},
            {"time": {"elapsed": 70, "extra": None}, "team": {"name": "Cruzeiro"}, "player": {"name": "Jogador D"}, "assist": {"name": None}, "type": "Goal", "detail": "Penalty"},
        ]
        stats = [
            {"team": {"name": "Cruzeiro"}, "statistics": [{"type": "Ball Possession", "value": "55%"}, {"type": "Total Shots", "value": 14}, {"type": "Corner Kicks", "value": 6}, {"type": "Fouls", "value": 9}]},
            {"team": {"name": "Fluminense"}, "statistics": [{"type": "Ball Possession", "value": "45%"}, {"type": "Total Shots", "value": 7}, {"type": "Corner Kicks", "value": 2}, {"type": "Fouls", "value": 11}]},
        ]
        # status "PRV" e finalized=1: nunca são repostados nem consultados na API
        fut = dict(base, fixture_id=9_000_000_001, kickoff=now + 2 * 86400, status="PRV", home_goals=None, away_goals=None)
        fin = dict(base, fixture_id=9_000_000_002, kickoff=now - 3 * 3600, status="PRV", home_goals=2, away_goals=0,
                   detail=json.dumps({"events": events, "statistics": stats, "referee": "Árbitro Exemplo"}))
        await bot.db.insert_match(fut, finalized=1)
        await bot.db.insert_match(fin, finalized=1)
        ch_p, ch_r = await bot.channel(g["partidas_ch"]), await bot.channel(g["resultados_ch"])
        fut2 = dict(fut, fixture_id=9_000_000_003, home="Grêmio", away="Internacional", kickoff=now + 2 * 86400 + 5400,
                    venue="Arena do Grêmio", city="Porto Alegre")
        await bot.db.insert_match(fut2, finalized=1)
        if ch_p:
            rows = [await bot.db.get_match(9_000_000_001), await bot.db.get_match(9_000_000_003)]
            emb, view = await bot.make_container(rows)
            await ch_p.send("**[EXEMPLO]**", embed=emb, view=view)
        if ch_r:
            fm = await bot.db.get_match(9_000_000_002)
            await ch_r.send("**[EXEMPLO]**", embed=embeds.resultado_embed(fm, await bot.emo_for(fm)), view=resultado_view(9_000_000_002))
            live = dict(fin, fixture_id=9_000_000_004, status="2H", elapsed=67, home_goals=1, away_goals=0, away="Botafogo",
                        detail=json.dumps({"events": events[:1], "statistics": []}))
            await bot.db.insert_match(live, finalized=1)
            lm = await bot.db.get_match(9_000_000_004)
            await ch_r.send("**[EXEMPLO AO VIVO]**", embed=embeds.live_embed(lm, await bot.emo_for(lm)))
            await ch_r.send("**[EXEMPLO DE ALERTA]**\n⚽ **GOOOL do Cruzeiro!** Cruzeiro **1** X **0** Botafogo — 67'\n⚽ `67'` **Jogador A** (Cruzeiro)")
        await i.followup.send("✅ Exemplos postados. Teste os botões Palpitar, Súmula e Estatísticas.", ephemeral=True)

    @tree.command(name="rank", description="Mostra o ranking de palpites")
    @app_commands.guild_only()
    async def rank(i: discord.Interaction):
        await i.response.send_message(embed=embeds.ranking_embed(await bot.db.ranking(i.guild_id)), ephemeral=True)

    @tree.command(name="meuspalpites", description="Seus últimos palpites")
    @app_commands.guild_only()
    async def meuspalpites(i: discord.Interaction):
        rows = await bot.db.user_predictions(i.guild_id, i.user.id)
        if not rows:
            return await i.response.send_message("Você ainda não palpitou.", ephemeral=True)
        lines = []
        for r in rows:
            res = f" → {r['home_goals']}x{r['away_goals']} (**+{r['points']}**)" if r["points"] is not None else ""
            lines.append(f"{r['home']} **{r['ph']} x {r['pa']}** {r['away']}{res}")
        await i.response.send_message("\n".join(lines), ephemeral=True)


if __name__ == "__main__":
    if not config.DISCORD_TOKEN or not config.API_FOOTBALL_KEY:
        raise SystemExit("Preencha DISCORD_TOKEN e API_FOOTBALL_KEY no .env")
    GingaBot().run(config.DISCORD_TOKEN, log_handler=None)