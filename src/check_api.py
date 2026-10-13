"""Teste rápido da chave da API-Football. Rode antes de subir o bot:  python check_api.py"""
import asyncio
from datetime import date

import aiohttp

import config
from src.api import ApiError, ApiFootball


async def main():
    async with aiohttp.ClientSession() as s:
        api = ApiFootball(config.API_FOOTBALL_KEY, s, config.TIMEZONE)
        try:
            items = await api.fixtures_by_date(date.today().isoformat())
        except ApiError as e:
            print("❌ A API recusou a chave/consulta:", e)
            print("   Se a mensagem fala de 'season' ou 'plan', o plano grátis não cobre a temporada atual.")
            return
        mine = [i for i in items if i["league"]["id"] in config.LEAGUES]
        print(f"✅ API ok. {len(items)} jogos hoje no mundo, {len(mine)} nas suas ligas:")
        for i in mine:
            print(f"  - {i['league']['name']}: {i['teams']['home']['name']} x {i['teams']['away']['name']} ({i['fixture']['status']['short']})")


asyncio.run(main())


async def test_next():
    """Testa se o plano deixa buscar 'próximos jogos' por liga (fora da janela de datas)."""
    async with aiohttp.ClientSession() as s:
        api = ApiFootball(config.API_FOOTBALL_KEY, s, config.TIMEZONE)
        for league, season in [(71, 2026), (39, 2026), (13, 2026)]:
            try:
                items = await api._get("/fixtures", {"league": league, "season": season, "next": 10, "timezone": config.TIMEZONE})
                print(f"✅ liga {league}: consulta 'next' funcionou ({len(items)} jogos)")
                for i in items[:3]:
                    print("   ", i["fixture"]["date"], i["teams"]["home"]["name"], "x", i["teams"]["away"]["name"])
            except ApiError as e:
                print(f"❌ liga {league}: {e}")


asyncio.run(test_next())