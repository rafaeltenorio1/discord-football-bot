# Football Bot for Discord

🇧🇷 [Leia em português](README.md)

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.5%2B-5865F2?logo=discord&logoColor=white)

A Python bot that follows the main football competitions in your Discord server: a match schedule grouped by competition, live scores, results with match report and statistics, goal alerts, and a prediction leaderboard among members.

Built for friend groups and small communities, it runs on the **free tiers** of the data APIs (with some limitations, described in [Free-tier limits](#free-tier-limits)).

> **Language note:** the bot's messages and slash command names are currently in **Brazilian Portuguese** (e.g. `/configurar`, `/ligas`). Command names are listed in [Commands](#commands) with their meaning.
>
> Independent project, not affiliated with Discord, the leagues, the clubs or the data providers mentioned.

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Installation](#installation)
- [Configuration](#configuration)
- [Commands](#commands)
- [Predictions and scoring](#predictions-and-scoring)
- [Free-tier limits](#free-tier-limits)
- [Hosting](#hosting)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)
- [Known limitations and roadmap](#known-limitations-and-roadmap)
- [Privacy and license](#privacy-and-license)

## Features

- **Upcoming matches by competition:** one message (container) per competition, with date, countdown, stadium and team crests. The order of competitions is configurable.
- **Predictions via menu and modal:** each container has a dropdown to pick a match; the score is typed into a pop-up form. Predictions can be edited until kickoff.
- **Live score:** when a match starts, the bot posts a "🔴 AO VIVO" (live) message and keeps updating it with score, minute, half-time and goal scorers.
- **Final result:** the same message turns into the result, with **Súmula** (match report: goals, cards, substitutions, referee) and **Estatísticas** (statistics: possession, shots, corners, fouls, etc.) buttons.
- **Goal alerts:** a new message for every goal (or disallowed goal), which triggers a Discord notification. You can ping a role and choose which competitions send alerts.
- **Prediction leaderboard:** a pinned message updated after every finished match, plus a summary of who scored points.
- **API quota protection:** the bot adapts how often it polls to the quota left for the day.

### Included competitions

Brasileirão Série A, Copa do Brasil, Copa Libertadores, UEFA Champions League, Premier League, La Liga, FIFA World Cup and UEFA Nations League. You can add others (see [Adding a competition](#adding-a-competition)).

### What the messages look like

<img src="https://i.ibb.co/twr8V4s9/game-mensage.png" alt="Futuros Jogos" width="300"> <img src="https://i.ibb.co/gLph6PZt/llive-game.png" alt="Futuros Jogos" width="300"> <img src="https://i.ibb.co/97NBVWL/game-final.png" alt="Futuros Jogos" width="300">


Run `/preview` after installing to see the real thing in your server without using any API quota.

## How it works

| Task | Frequency | Source |
| --- | --- | --- |
| Fetch the schedule for upcoming matches | every 3 h | football-data.org (full round) and API-Football (today and tomorrow) |
| Update the score of matches in progress | every 3 to 15 min, depending on quota | API-Football |
| Fetch final match report and statistics | once per match, when it ends | API-Football |
| Post, edit and remove messages | on every change | Discord (does not use API quota) |

The same match is recognized across both APIs by competition, kickoff time and team-name similarity. Data is stored in a local SQLite database (`data/bot.db`).

## Installation

### Requirements

- **Python 3.10 or newer**
- A Discord account with permission to manage the server
- API keys (free): [API-Football](https://www.api-football.com/) and, optionally, [football-data.org](https://www.football-data.org/)

### 1. Create the bot application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. In the **Bot** tab, click **Reset Token** and save the token. It is a password: never share or publish it.
3. You do **not** need to enable any *Privileged Gateway Intent*.
4. Under **OAuth2 → URL Generator**, select the `bot` and `applications.commands` scopes and these permissions:
   - Send Messages
   - Embed Links
   - Read Message History
   - Manage Messages (pin the leaderboard and delete the bot's own old messages)
   - Mention Everyone (only if you want to ping a role in goal alerts)
5. Open the generated link and add the bot to your server.

### 2. Get the API keys

- **API-Football** (required): create an account, copy the key from the dashboard and use it as `API_FOOTBALL_KEY`.
- **football-data.org** (optional, recommended): create a free account and use the token as `FOOTBALL_DATA_TOKEN`. Without it, the bot only shows matches from yesterday to tomorrow.

### 3. Install and configure

```bash
git clone https://github.com/rafaeltenorio1/discord-football-bot
cd src

python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt

# Linux/macOS:
cp .env.example .env
# Windows:
copy .env.example .env
```

Edit `.env` and fill in at least `DISCORD_TOKEN` and `API_FOOTBALL_KEY` (see [Configuration](#configuration)).

Test your API-Football key before starting (uses 1 request):

```bash
python check_api.py
```

### 4. Run

```bash
python bot.py
```

In Discord, create three text channels (for example `#partidas`, `#resultados` and `#ranking`) and run:

```
/configurar partidas:#partidas resultados:#resultados ranking:#ranking
```

Then use `/preview` to check the look and `/ligas` to pick the competitions.

> Tip: set `DEV_GUILD_ID` to your server's ID so slash commands show up immediately. Without it, Discord can take a while to display them.

## Configuration

All options live in the `.env` file.

| Variable | Default | Description |
| --- | --- | --- |
| `DISCORD_TOKEN` | – | **Required.** Bot token. |
| `API_FOOTBALL_KEY` | – | **Required.** API-Football key. |
| `FOOTBALL_DATA_TOKEN` | empty | football-data.org token. Enables the full upcoming schedule for Brasileirão, Premier League, La Liga, Champions League and World Cup. |
| `TIMEZONE` | `America/Brasilia` | Time zone used to group matches by day. Use an IANA time zone name (e.g. `America/Sao_Paulo`, `Europe/London`). |
| `FD_DAYS_AHEAD` | `7` | How many days ahead to fetch from football-data.org. |
| `DAYS_AHEAD` | `1` | Days ahead on API-Football. The free plan allows at most 1 (today and tomorrow). |
| `LIVE_LEAGUES` | all | Comma-separated IDs of competitions with live score (e.g. `71,13`). Others only update at full time. |
| `LIVE_INTERVAL_MINUTES` | `3` | Minimum interval between live polls. It increases automatically as the quota drops. |
| `LIVE_SCORERS` | `1` | `1` looks up each goal scorer (1 extra request per goal, only when quota allows). `0` shows the score only. |
| `ALERT_DELETE_MINUTES` | `0` | Deletes each goal alert after N minutes. `0` keeps them all. |
| `DB_PATH` | `data/bot.db` | Path of the SQLite database. |
| `DEV_GUILD_ID` | empty | Server ID to register commands instantly (useful while testing). |
| `PORT` | empty | If set, the bot opens an HTTP port that answers `ok`, required by some hosting platforms. |

### Competition order and icons

Competitions are listed in `LEAGUES` in `config.py`. **The order of that list is the order of the containers in the matches channel.** To replace a competition's emblem, add `"icon": "https://.../image.png"` to its entry.

### Adding a competition

1. Find the league ID on API-Football.
2. Add a line to `LEAGUES` in `config.py`:
   ```python
   135: {"name": "Serie A (Italy)", "split": True},   # split=True for European seasons (2026/27)
   ```
3. Restart the bot and enable the competition with `/ligas`.

Competitions added this way rely only on API-Football and, on the free plan, appear one day in advance.

## Commands

Command names are in Portuguese. Admin commands require the **Manage Server** permission (adjustable in Discord's integration settings).

| Command | Who | What it does |
| --- | --- | --- |
| `/configurar` (configure) | Admin | Sets the matches, results and leaderboard channels. |
| `/ligas` (leagues) | Admin | Chooses which competitions the server follows. |
| `/alertas [cargo] [sem_cargo]` (alerts) | Admin | Sets the role pinged in goal alerts and the competitions they apply to. Deselect all to turn alerts off. |
| `/sincronizar` (sync) | Admin | Fetches new matches now. Limited to once every 15 min to save quota. |
| `/repostar [atualizar]` (repost) | Admin | Deletes and re-posts all upcoming matches in `#partidas`. With `atualizar:True`, queries the APIs first. |
| `/preview` | Admin | Posts sample matches (upcoming, finished and live) so you can check the look. |
| `/rank` | Everyone | Shows the prediction leaderboard. |
| `/meuspalpites` (my predictions) | Everyone | Lists your latest predictions and points. |

## Predictions and scoring

| Situation | Points |
| --- | --- |
| Exact score | 3 |
| Correct winner only (or correct draw) | 1 |
| Wrong | 0 |

- Predictions close at kickoff and can be changed before that.
- In knockout matches, the score including extra time counts, without penalty shoot-outs.
- Leaderboard tiebreakers: points, then exact scores, then correct outcomes.
- Values can be changed in `config.py` (`PTS_EXACT` and `PTS_OUTCOME`).

## Free-tier limits

The free plans have restrictions that shape how the bot works:

**API-Football (free)**
- 100 requests per day.
- Only allows querying **yesterday, today and tomorrow**, and does not accept batch lookup by ID.
- Because of that, competitions covered only by it (Libertadores, Copa do Brasil, Nations League) appear at most 1 day in advance.

**football-data.org (free)**
- Covers Brasileirão, Premier League, La Liga, Champions League and World Cup, with the full schedule.
- Scores are delayed and detailed statistics are not available. The bot therefore uses this source for the schedule only, and API-Football for live score, match report and statistics.

**API-Football request usage**
- Schedule: about 16 per day.
- Live score: 1 request returns all matches of a date, so simultaneous matches cost the same as one.
- Full time: 1 request per match for report and statistics.
- Goals (if `LIVE_SCORERS=1`): 1 request per goal to identify the scorer.
- The polling interval grows as the quota drops (3, 5, 8 and 15 minutes). With fewer than 8 requests left, the bot saves what remains for final results; with fewer than 3, it stops polling.

On days with many matches at different times the quota can get tight and goals may show up a few minutes late. A paid plan removes these restrictions (check the providers' websites for current plans).

## Hosting

The bot must stay **running all the time** and **keep the `data/bot.db` file**, which holds predictions and the leaderboard.

Hosting requirements:
- Python 3.10+ and a continuously running process.
- **Persistent disk.** Platforms that wipe the disk on every restart will reset the leaderboard unless you configure a persistent volume.
- Outbound HTTPS access to `discord.com`, `v3.football.api-sports.io`, `media.api-sports.io` and `api.football-data.org`.
- If the platform requires an open port, set `PORT`.

Common options: your own machine running 24/7, a mini PC/Raspberry Pi, a VPS or a cloud VM. Free-tier terms and limits change often, so check current conditions before choosing.

### Example: systemd service (Linux)

File `/etc/systemd/system/football-bot.service`, adjusting paths and user:

```ini
[Unit]
Description=Football Bot for Discord
After=network-online.target

[Service]
User=YOUR_USER
WorkingDirectory=/path/to/project
ExecStart=/path/to/project/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now football-bot
journalctl -u football-bot -f   # follow the logs
```

Back up `data/bot.db` regularly.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| `No time zone found with key America/Brasilia` | The `tzdata` package is not installed in the same Python that runs the bot (common on Windows). Run `python -m pip install -r requirements.txt`. Using `python -m pip` guarantees pip and Python match. |
| `Free plans do not have access to this date` | The API-Football free plan only accepts yesterday, today and tomorrow. Keep `DAYS_AHEAD=1`. |
| `Free plans do not have access to this season` | The free plan does not allow current-season queries. The bot already avoids them; if you see this in your own tests, query by date instead. |
| `Free plans do not have access to the Ids parameter` | Batch lookup is not available on the free plan. Update to the latest version of the bot. |
| Slash commands do not show up | Set `DEV_GUILD_ID` to your server ID and restart. Check that the bot was added with the `applications.commands` scope. |
| I deleted the messages and the bot did not resend the matches | The bot remembers what it already posted. Use `/repostar`. |
| Team crests do not show | Check the log: `getaddrinfo failed` means a DNS/network problem while downloading the image (try `https://media.api-sports.io/football/teams/42.png` in your browser). SVG crests are not supported. Also check the bot's "Use External Emojis" permission. The bot retries every 10 minutes. |
| Warning `PyNaCl is not installed` or `Privileged message content intent is missing` | Can be ignored: they only affect voice and prefix commands, which the bot does not use. |
| Goals show up late | Expected on the free plan when quota runs low. Use `LIVE_LEAGUES` to limit live competitions, or consider a paid plan. |
| A match appeared without report/statistics | The bot could not match the game across the two APIs. The result is still posted, using the fallback source's score. |

## Project structure

```
bot.py          Bot, commands, scheduled tasks, live messages and alerts
api.py          API-Football and football-data.org clients
db.py           SQLite database (matches, predictions, posted messages, settings)
embeds.py       Message building (containers, score, report, statistics, leaderboard)
merge.py        Matches the same game across the two APIs
logic.py        Scoring, match statuses and adaptive polling interval
config.py       Options, competitions and scoring
check_api.py    Quick test of the API-Football key
```

## Known limitations and roadmap

- Team names come from the APIs (some in English) and may differ between sources.
- The stadium is not always available for distant matches; it shows up once the match enters API-Football's window.
- If the bot starts in the middle of a match, it does not alert for goals scored before that.
- The order of who comes on and who goes off in the match report's substitutions follows our reading of the API documentation; if it looks inverted, adjust it in `embeds.py`.
- **Planned:** e-sports support (for example, Rainbow Six), with a data source to be defined.
- Bot messages and command names are in Portuguese only for now.

Suggestions and fixes are welcome through issues and pull requests.

## Privacy and license

The bot stores locally, in `data/bot.db`, only Discord user IDs, predictions and server settings. It does not read the content of members' messages.

Crests and emblems belong to their respective clubs and competitions; the data belongs to the providers, and its use is subject to each API's terms.

This project does not define a license yet. Until a `LICENSE` file is added, all rights remain reserved to the author.