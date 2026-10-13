from src import config

FINISHED = {"FT", "AET", "PEN"}
DEAD = {"CANC", "ABD", "AWD", "WO"}


def outcome(h: int, a: int) -> int:
    return (h > a) - (h < a)


def score_prediction(ph: int, pa: int, rh: int, ra: int) -> int:
    if ph == rh and pa == ra:
        return config.PTS_EXACT
    if outcome(ph, pa) == outcome(rh, ra):
        return config.PTS_OUTCOME
    return 0

LIVE = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "SUSP", "INT"}


def live_interval(remaining, base: int):
    """Minutos entre consultas ao vivo, conforme a cota que sobrou no dia. None = modo reserva."""
    if remaining is None or remaining >= 60:
        return base
    if remaining >= 40:
        return base + 2
    if remaining >= 20:
        return base + 5
    if remaining >= 8:
        return base + 12
    return None