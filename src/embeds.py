import json
from datetime import datetime

import discord

import config

COLOR = 0xD9C98B


def league_label(m) -> str:
    info = config.LEAGUES.get(m["league_id"], {})
    name = info.get("name") or m["league_name"]
    s = m["season"]
    if s and info.get("split"):
        return f"{name} {s}/{str(s + 1)[2:]}"
    return f"{name} {s}" if s else name


def when(ts: int) -> str:
    # <t:..:f> mostra "22 de junho de 2024 às 16:00" no Discord em português
    return f"<t:{ts}:f> | (<t:{ts}:R>)"


def where(m) -> str:
    parts = [p for p in (m["venue"], m["city"]) if p]
    return ", ".join(parts) if parts else "Estádio a definir"


def partida_embed(m) -> discord.Embed:
    e = discord.Embed(
        title=f"{m['home']} X {m['away']}",
        description=f"🏆 {league_label(m)}\n🗓️ {when(m['kickoff'])}\n🏟️ {where(m)}",
        color=COLOR,
    )
    if m["league_logo"]:
        e.set_thumbnail(url=m["league_logo"])
    if m["round"]:
        e.set_footer(text=m["round"])
    return e


def _crests(m, emo):
    emo = emo or {}
    he, ae = emo.get(m["home_logo"], ""), emo.get(m["away_logo"], "")
    return (he + " " if he else ""), (" " + ae if ae else "")


def resultado_embed(m, emo=None) -> discord.Embed:
    he, ae = _crests(m, emo)
    e = discord.Embed(
        title=f"{he}{m['home']} {m['home_goals']} X {m['away_goals']} {m['away']}{ae}",
        description=f"🗓️ {when(m['kickoff'])}\n🏟️ {where(m)}",
        color=COLOR,
    )
    e.set_author(name=league_label(m), icon_url=m["league_logo"] or None)
    return e


LIVE_LABEL = {"1H": "1º tempo", "HT": "Intervalo", "2H": "2º tempo", "ET": "Prorrogação",
              "BT": "Intervalo da prorrogação", "P": "Pênaltis", "LIVE": "Ao vivo",
              "SUSP": "Jogo paralisado", "INT": "Jogo interrompido"}


def goal_lines(detail) -> list[str]:
    d = json.loads(detail) if detail else {}
    out = []
    for ev in sorted(d.get("events", []), key=lambda x: ((x["time"].get("elapsed") or 0), (x["time"].get("extra") or 0))):
        det = ev.get("detail") or ""
        if ev.get("type") != "Goal" or "Missed" in det:
            continue
        t = ev["time"].get("elapsed") or 0
        if ev["time"].get("extra"):
            t = f"{t}+{ev['time']['extra']}"
        who = (ev.get("player") or {}).get("name") or "?"
        tag = " (pênalti)" if "Penalty" in det else " (contra)" if "Own" in det else ""
        out.append(f"⚽ `{t}'` **{who}**{tag} ({ev['team']['name']})")
    return out


def live_embed(m, emo=None) -> discord.Embed:
    he, ae = _crests(m, emo)
    hg = m["home_goals"] if m["home_goals"] is not None else 0
    ag = m["away_goals"] if m["away_goals"] is not None else 0
    label = LIVE_LABEL.get(m["status"], "Ao vivo")
    status = f"{m['elapsed']}' · {label}" if m["elapsed"] and m["status"] in ("1H", "2H", "ET") else label
    lines = [f"🔴 **AO VIVO** — {status}"]
    goals = goal_lines(m["detail"])
    if goals:
        lines.append("\n".join(goals))
    lines.append(f"🏟️ {where(m)}")
    e = discord.Embed(
        title=f"{he}{m['home']} {hg} X {ag} {m['away']}{ae}",
        description="\n\n".join(lines)[:4000],
        color=0xE74C3C,
    )
    e.set_author(name=league_label(m), icon_url=m["league_logo"] or None)
    return e


EVENT_ICON = {"Yellow Card": "🟨", "Red Card": "🟥", "Second Yellow card": "🟨🟥"}


def sumula_embed(m) -> discord.Embed:
    d = json.loads(m["detail"]) if m["detail"] else {}
    events = sorted(
        d.get("events", []),
        key=lambda x: ((x["time"].get("elapsed") or 0), (x["time"].get("extra") or 0)),
    )
    lines = []
    for ev in events:
        t = ev["time"].get("elapsed") or 0
        if ev["time"].get("extra"):
            t = f"{t}+{ev['time']['extra']}"
        team = ev["team"]["name"]
        who = (ev.get("player") or {}).get("name") or "?"
        typ, det = ev.get("type"), ev.get("detail") or ""
        if typ == "Goal":
            extra = " (pênalti)" if "Penalty" in det and "Missed" not in det else " (contra)" if "Own" in det else ""
            if "Missed" in det:
                lines.append(f"`{t}'` ❌ Pênalti perdido — **{who}** ({team})")
                continue
            assist = (ev.get("assist") or {}).get("name")
            lines.append(f"`{t}'` ⚽ **{who}**{extra} ({team})" + (f" — assist. {assist}" if assist else ""))
        elif typ == "Card":
            lines.append(f"`{t}'` {EVENT_ICON.get(det, '🟨')} **{who}** ({team})")
        elif typ == "subst":
            came_in = (ev.get("assist") or {}).get("name") or "?"
            lines.append(f"`{t}'` 🔄 {team}: entra **{came_in}**, sai {who}")
    e = discord.Embed(
        title=f"Súmula — {m['home']} {m['home_goals']} X {m['away_goals']} {m['away']}",
        description=("\n".join(lines) or "Sem eventos registrados.")[:3900],
        color=COLOR,
    )
    info = [f"🏆 {league_label(m)}", f"🏟️ {where(m)}"]
    if d.get("referee"):
        info.append(f"🧑‍⚖️ Árbitro: {d['referee']}")
    e.add_field(name="Informações", value="\n".join(info), inline=False)
    return e


STAT_LABELS = [
    ("Ball Possession", "Posse de bola"),
    ("Total Shots", "Finalizações"),
    ("Shots on Goal", "Chutes no gol"),
    ("Shots off Goal", "Chutes para fora"),
    ("Blocked Shots", "Chutes bloqueados"),
    ("Corner Kicks", "Escanteios"),
    ("Fouls", "Faltas"),
    ("Offsides", "Impedimentos"),
    ("Yellow Cards", "Cartões amarelos"),
    ("Red Cards", "Cartões vermelhos"),
    ("Goalkeeper Saves", "Defesas do goleiro"),
    ("Total passes", "Passes"),
    ("Passes %", "Precisão de passes"),
    ("expected_goals", "Gols esperados (xG)"),
]


def stats_embed(m):
    d = json.loads(m["detail"]) if m["detail"] else {}
    stats = d.get("statistics", [])
    if len(stats) < 2:
        return None
    a = {s["type"]: s["value"] for s in stats[0]["statistics"]}
    b = {s["type"]: s["value"] for s in stats[1]["statistics"]}
    lines = []
    for key, label in STAT_LABELS:
        if key not in a and key not in b:
            continue
        va = a.get(key) if a.get(key) is not None else 0
        vb = b.get(key) if b.get(key) is not None else 0
        lines.append(f"`{str(va):>6}`  **{label}**  `{str(vb):<6}`")
    e = discord.Embed(
        title=f"Estatísticas — {m['home']} X {m['away']}",
        description=f"**{m['home']}** ‹ › **{m['away']}**\n\n" + "\n".join(lines),
        color=COLOR,
    )
    e.set_author(name=league_label(m), icon_url=m["league_logo"] or None)
    return e


def container_embed(rows, emo: dict) -> discord.Embed:
    """Um embed por competição, com todos os jogos dentro (estilo Ginga)."""
    first = rows[0]
    blocks = []
    for m in sorted(rows, key=lambda r: r["kickoff"]):
        he, ae = emo.get(m["home_logo"], ""), emo.get(m["away_logo"], "")
        title = f"**{he + ' ' if he else ''}{m['home']} X {m['away']}{' ' + ae if ae else ''}**"
        blocks.append(f"{title}\n> 🗓️ {when(m['kickoff'])}\n> 🏟️ {where(m)}")
    e = discord.Embed(description="\n\n".join(blocks), color=COLOR)
    icon = config.LEAGUES.get(first["league_id"], {}).get("icon") or first["league_logo"] or None
    e.set_author(name=league_label(first), icon_url=icon)
    return e


MEDALS = ["🥇", "🥈", "🥉"]


def ranking_embed(rows) -> discord.Embed:
    if not rows:
        desc = "Ninguém pontuou ainda. Dê seus palpites no canal de partidas! 🎯"
    else:
        out = []
        for i, r in enumerate(rows):
            pos = MEDALS[i] if i < 3 else f"`{i + 1}º`"
            out.append(f"{pos} <@{r['user_id']}> — **{r['pts']} pts** · {r['exact']} cravadas · {r['hits']} acertos · {r['n']} jogos")
        desc = "\n".join(out)
    e = discord.Embed(title="🏆 Ranking de palpites", description=desc, color=COLOR)
    e.set_footer(text=f"Placar exato = {config.PTS_EXACT} pts · Vencedor/empate = {config.PTS_OUTCOME} pt")
    e.timestamp = datetime.now()
    return e