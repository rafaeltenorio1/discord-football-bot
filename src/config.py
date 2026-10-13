import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
DB_PATH = os.getenv("DB_PATH", "../data/bot.db")
TIMEZONE = os.getenv("TIMEZONE", "America/Belem")
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "1"))   # dias à frente (plano grátis da API: máx. 1)
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")  # opcional: football-data.org (rodada completa)
FD_DAYS_AHEAD = int(os.getenv("FD_DAYS_AHEAD", "7"))        # dias à frente buscados no football-data.org
LIVE_SCORERS = os.getenv("LIVE_SCORERS", "1") == "1"  # buscar quem fez o gol (1 req extra por gol, só com cota folgada)
LIVE_INTERVAL_MINUTES = int(os.getenv("LIVE_INTERVAL_MINUTES", "3"))  # intervalo mínimo entre consultas ao vivo
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID")
PORT = os.getenv("PORT")                         # hospedagens tipo Render exigem uma porta aberta

# Pontuação dos palpites
PTS_EXACT = 3     # placar exato
PTS_OUTCOME = 1   # acertou só o vencedor (ou empate)

# A ORDEM desta lista é a ordem dos containers no canal #partidas (de cima para baixo).
# Opcional: "icon": "https://...png" troca o emblema da competição por uma imagem sua.
# IDs de liga da API-Football. "split" = temporada europeia (2026/27)
LEAGUES = {
    71:  {"name": "Brasileirão - Série A", "split": False},
    73:  {"name": "Copa do Brasil",        "split": False},
    13:  {"name": "Copa Libertadores",     "split": False},
    2:   {"name": "UEFA Champions League", "split": True},
    39:  {"name": "Premier League",        "split": True},
    140: {"name": "La Liga",               "split": True},
    1:   {"name": "Copa do Mundo",         "split": False},
    5:   {"name": "UEFA Nations League",   "split": True},
}

# Competições cobertas pelo plano grátis do football-data.org -> ID da liga na API-Football
FD_COMPETITIONS = {"BSA": 71, "PL": 39, "PD": 140, "CL": 2, "WC": 1}
FD_OFFSET = 1_000_000_000  # jogos que só existem no football-data.org usam este deslocamento no ID interno

# Competições em que o placar é atualizado a cada gol (as demais só atualizam no fim do jogo).
# Padrão: todas. Para limitar: LIVE_LEAGUES=71,13 no .env
_live = [int(x) for x in os.getenv("LIVE_LEAGUES", "").replace(" ", "").split(",") if x]
LIVE_LEAGUES = set(_live) if _live else set(LEAGUES)

# Minutos até apagar cada alerta de gol (0 = não apagar)
ALERT_DELETE_MINUTES = int(os.getenv("ALERT_DELETE_MINUTES", "0"))