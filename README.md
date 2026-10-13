# Bot de futebol para Discord (estilo Ginga)

Três canais: **#partidas** (próximos jogos + botão Palpitar), **#resultados** (placar + botões Súmula e Estatísticas) e **#ranking** (ranking de palpites).

## 1. Criar o bot no Discord
1. https://discord.com/developers/applications → **New Application**.
2. Aba **Bot** → **Reset Token** → copie para `DISCORD_TOKEN` no `.env`. Não precisa ligar nenhum "Privileged Intent".
3. Aba **OAuth2 → URL Generator**: marque `bot` + `applications.commands`. Permissões: *Send Messages, Embed Links, Read Message History, Manage Messages* (para fixar o ranking). Abra o link gerado e adicione ao seu servidor.

## 2. Chave da API de futebol
Crie conta em **api-football.com** (plano grátis: 100 requisições/dia) e copie a chave para `API_FOOTBALL_KEY`.
Depois rode `python check_api.py`. **Esse teste é importante:** o plano grátis limita as temporadas disponíveis; se ele mostrar erro de `season`/`plan`, o grátis não cobre 2026 e será preciso o plano pago (a partir de ~US$19/mês, 7.500 req/dia) ou trocar de fonte.

## 3. Rodar
```
pip install -r requirements.txt
cp .env.example .env     # preencha as chaves
python bot.py
```
No Discord, crie os 3 canais e use `/configurar partidas:#... resultados:#... ranking:#...`.

## Comandos
`/configurar` · `/ligas` (escolher competições) · `/alertas` · `/repostar` (apaga e reposta os jogos futuros em #partidas; `atualizar:True` busca nas APIs antes) · `/sincronizar` · `/preview` (posta jogos de exemplo para ver o visual) · `/rank` · `/meuspalpites`

## Pontuação
Placar exato = 3 pts · acertar vencedor/empate = 1 pt (mude em `config.py`). Palpites fecham no início do jogo e podem ser editados antes. Em mata-mata vale o placar com prorrogação, sem pênaltis.

## Hospedagem gratuita (IMPORTANTE)
Os palpites ficam num arquivo SQLite (`DB_PATH`). Muitas hospedagens grátis **apagam o disco** a cada reinício, o que zeraria o ranking. Use uma que tenha volume/disco persistente, ou uma VM gratuita. Se a hospedagem exigir porta aberta, defina `PORT` e o bot responde um "ok" na raiz. Termos de planos grátis mudam com frequência, confira o atual antes de escolher.

## Canal #partidas: um container por competição
- Cada competição vira uma mensagem (container) com todos os jogos dentro, e um menu "Escolha um jogo para palpitar" embaixo. Containers com mais de 25 jogos são divididos.
- A ordem dos containers (de cima para baixo) é a ordem de `LEAGUES` em `config.py`. Reordene lá se quiser.
- Jogos novos entram no container existente da competição; quando um jogo termina ele sai do container (e vai para #resultados). Container vazio é apagado.
- Para trocar o emblema de uma competição por outra imagem, adicione `"icon": "https://...png"` na linha dela em `config.py`.
- **Escudos:** o bot baixa o escudo de cada time e o envia ao Discord como *emoji de aplicação* (fica na sua aplicação, funciona em qualquer servidor). Só aceita PNG/JPG até 256 KB; escudos em SVG são ignorados e o jogo aparece só com texto. Precisa de discord.py 2.5+.

## Alertas de gol (notificação)
O Discord não notifica quando uma mensagem é editada, então a cada gol (e a cada gol anulado pelo VAR) o bot envia uma mensagem nova e curta no #resultados, que gera notificação normal. Comando: `/alertas`.
- `/alertas cargo:@Futebol` marca esse cargo em cada alerta (quem quiser ser avisado entra no cargo). `/alertas sem_cargo:True` para de marcar.
- O comando abre um menu para escolher em quais competições o alerta vale. Desmarque todas para desligar. Vale na hora, sem reiniciar.
- Padrão: alerta ligado para todas as competições, sem cargo. Para o bot poder marcar um cargo, ele precisa de permissão no canal e o cargo precisa estar liberado para ser mencionado (ou o bot ter "Mencionar @everyone, @here e todos os cargos").
- `ALERT_DELETE_MINUTES` no `.env` apaga cada alerta depois de N minutos (0 = manter).
- Não alerta o placar que já existia quando o bot foi ligado no meio do jogo.

## Duas APIs combinadas
- **football-data.org (grátis, opcional):** traz a rodada completa dos próximos `FD_DAYS_AHEAD` dias para Brasileirão, Premier League, La Liga, Champions e Copa do Mundo. Crie conta, copie o token para `FOOTBALL_DATA_TOKEN`.
- **API-Football (plano grátis):** só enxerga ontem, hoje e amanhã. Fornece estádio, escudos, **súmula e estatísticas**, e é quem detecta o fim do jogo. É a única fonte de Libertadores, Copa do Brasil e Nations League, que por isso aparecem só com 1 dia de antecedência.
- O bot casa o mesmo jogo nas duas APIs por liga + horário + semelhança dos nomes. Se não conseguir casar, o jogo aparece sem súmula/estatísticas (o resultado vem do football-data.org, com atraso).

## Consumo da API-Football (100/dia)
- Busca de jogos: 2 req a cada 3 h ≈ 16/dia. O bot não busca de novo se for reiniciado antes de 3 h.
- **Placar ao vivo e resultados:** quando um jogo começa, o bot posta no #resultados uma mensagem "🔴 AO VIVO" e a **edita** a cada gol, no intervalo e no fim, quando ela vira o resultado final com os botões Súmula e Estatísticas. Editar mensagem não gasta API. O plano grátis não aceita consulta em lote por ID, então o bot consulta por **data**: 1 requisição traz todos os jogos do dia, então jogos simultâneos custam o mesmo que um. Quando o jogo termina, mais 1 requisição busca a súmula e as estatísticas finais. Se `LIVE_SCORERS=1` e a cota estiver folgada (30+), cada gol custa 1 requisição extra para mostrar quem marcou.
- **Cota protegida:** o intervalo entre consultas aumenta conforme a cota do dia diminui (padrão: 3 min com 60+ restantes, 5 min com 40+, 8 min com 20+, 15 min com 8+). Com menos de 8 restantes, o bot guarda o que sobrou só para os resultados finais; com menos de 3 para de consultar.
- Para gastar menos, limite as competições ao vivo com `LIVE_LEAGUES` (ex.: `LIVE_LEAGUES=71,13`); as demais só atualizam no fim do jogo. `LIVE_INTERVAL_MINUTES` muda o intervalo mínimo.
- No football-data.org grátis o placar é atrasado (ao vivo só no plano pago dele), por isso os gols vêm da API-Football.
- Súmula e estatísticas vêm na mesma resposta e ficam salvas: clicar nos botões não gasta nada.