# Bot de Futebol para Discord

🇺🇸 [Read in English](README.en.md)

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.5%2B-5865F2?logo=discord&logoColor=white)

Bot em Python que acompanha as principais competições de futebol no seu servidor do Discord: agenda de jogos organizada por competição, placar ao vivo, resultados com súmula e estatísticas, alertas de gol e um ranking de palpites entre os membros.

Pensado para servidores de amigos e comunidades pequenas, funciona com os **planos gratuitos** das APIs de dados (com algumas limitações, descritas em [Limites dos planos gratuitos](#limites-dos-planos-gratuitos)).

> Projeto independente, sem vínculo com a Discord, com as ligas, clubes ou provedores de dados citados.

## Sumário

- [Funcionalidades](#funcionalidades)
- [Como funciona](#como-funciona)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Comandos](#comandos)
- [Palpites e pontuação](#palpites-e-pontuação)
- [Limites dos planos gratuitos](#limites-dos-planos-gratuitos)
- [Hospedagem](#hospedagem)
- [Solução de problemas](#solução-de-problemas)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Limitações conhecidas e planos futuros](#limitações-conhecidas-e-planos-futuros)
- [Privacidade e licença](#privacidade-e-licença)

## Funcionalidades

- **Próximos jogos por competição:** uma mensagem (container) por competição, com data, contagem regressiva, estádio e os escudos dos times. A ordem das competições é configurável.
- **Palpites por menu e botão:** cada container tem um menu para escolher o jogo; o palpite é digitado numa janela. Pode ser alterado até o início da partida.
- **Placar ao vivo:** quando o jogo começa, o bot publica uma mensagem "🔴 AO VIVO" e a atualiza com placar, minuto, intervalo e autores dos gols.
- **Resultado final:** a mesma mensagem vira o resultado, com os botões **Súmula** (gols, cartões, substituições, árbitro) e **Estatísticas** (posse de bola, finalizações, escanteios, faltas etc.).
- **Alertas de gol:** mensagem nova a cada gol (ou gol anulado), que gera notificação no Discord. Dá para marcar um cargo e escolher as competições.
- **Ranking de palpites:** mensagem fixa atualizada a cada jogo encerrado, mais um resumo de quem pontuou.
- **Cota de API protegida:** o bot adapta a frequência das consultas à cota que sobrou no dia.

### Competições incluídas

Brasileirão Série A, Copa do Brasil, Copa Libertadores, UEFA Champions League, Premier League, La Liga, Copa do Mundo e UEFA Nations League. É possível acrescentar outras (veja [Adicionar uma competição](#adicionar-uma-competição)).

### Como as mensagens aparecem

<img src="https://i.ibb.co/twr8V4s9/game-mensage.png" alt="Futuros Jogos" width="300"> <img src="https://i.ibb.co/gLph6PZt/llive-game.png" alt="Futuros Jogos" width="300"> <img src="https://i.ibb.co/97NBVWL/game-final.png" alt="Futuros Jogos" width="300">


Use `/preview` depois de instalar para ver o visual real no seu servidor, sem gastar a API.

## Como funciona

| Tarefa | Frequência | Fonte |
| --- | --- | --- |
| Buscar a agenda dos próximos jogos | a cada 3 h | football-data.org (rodada completa) e API-Football (hoje e amanhã) |
| Atualizar placar dos jogos em andamento | a cada 3 a 15 min, conforme a cota | API-Football |
| Buscar súmula e estatísticas finais | 1 vez por jogo, ao terminar | API-Football |
| Postar, editar e remover mensagens | a cada mudança | Discord (não consome cota de API) |

O mesmo jogo é reconhecido nas duas APIs por competição, horário e semelhança dos nomes dos times. Os dados ficam em um banco SQLite local (`data/bot.db`).

## Instalação

### Requisitos

- **Python 3.10 ou superior**
- Uma conta no Discord com permissão de gerenciar o servidor
- Chaves das APIs (gratuitas): [API-Football](https://www.api-football.com/) e, opcionalmente, [football-data.org](https://www.football-data.org/)

### 1. Criar o aplicativo do bot

1. Acesse o [Discord Developer Portal](https://discord.com/developers/applications) e clique em **New Application**.
2. Na aba **Bot**, clique em **Reset Token** e guarde o token. Ele é uma senha: não compartilhe nem publique.
3. Não é necessário ativar nenhum *Privileged Gateway Intent*.
4. Em **OAuth2 → URL Generator**, marque os escopos `bot` e `applications.commands`, e as permissões:
   - Send Messages
   - Embed Links
   - Read Message History
   - Manage Messages (fixar o ranking e apagar mensagens antigas do próprio bot)
   - Mention Everyone (só se quiser marcar cargos nos alertas de gol)
5. Abra o link gerado e adicione o bot ao seu servidor.

### 2. Obter as chaves das APIs

- **API-Football** (obrigatória): crie uma conta, copie a chave do painel e use em `API_FOOTBALL_KEY`.
- **football-data.org** (opcional, recomendada): crie uma conta gratuita e use o token em `FOOTBALL_DATA_TOKEN`. Sem ela, o bot só mostra jogos de ontem a amanhã.

### 3. Instalar e configurar

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

Edite o arquivo `.env` e preencha ao menos `DISCORD_TOKEN` e `API_FOOTBALL_KEY` (veja [Configuração](#configuração)).

Teste a chave da API-Football antes de iniciar (gasta 1 requisição):

```bash
python check_api.py
```

### 4. Iniciar

```bash
python bot.py
```

No Discord, crie três canais de texto (por exemplo `#partidas`, `#resultados` e `#ranking`) e rode:

```
/configurar partidas:#partidas resultados:#resultados ranking:#ranking
```

Em seguida, use `/preview` para conferir o visual e `/ligas` para escolher as competições.

> Dica: preencha `DEV_GUILD_ID` com o ID do seu servidor para que os comandos `/` apareçam imediatamente. Sem isso, o Discord pode levar algum tempo para exibi-los.

## Configuração

Todas as opções ficam no arquivo `.env`.

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `DISCORD_TOKEN` | – | **Obrigatória.** Token do bot. |
| `API_FOOTBALL_KEY` | – | **Obrigatória.** Chave da API-Football. |
| `FOOTBALL_DATA_TOKEN` | vazio | Token do football-data.org. Habilita a agenda completa dos próximos dias para Brasileirão, Premier League, La Liga, Champions e Copa do Mundo. |
| `TIMEZONE` | `America/Brasilia` | Fuso usado para agrupar os jogos por dia. Use um nome de fuso IANA (ex.: `America/Sao_Paulo`). |
| `FD_DAYS_AHEAD` | `7` | Quantos dias à frente buscar no football-data.org. |
| `DAYS_AHEAD` | `1` | Dias à frente na API-Football. O plano gratuito aceita no máximo 1 (hoje e amanhã). |
| `LIVE_LEAGUES` | todas | IDs das competições com placar ao vivo, separados por vírgula (ex.: `71,13`). As demais só atualizam no fim do jogo. |
| `LIVE_INTERVAL_MINUTES` | `3` | Intervalo mínimo entre consultas ao vivo. Aumenta sozinho quando a cota diminui. |
| `LIVE_SCORERS` | `1` | `1` busca o autor de cada gol (1 requisição extra por gol, só com cota folgada). `0` mostra apenas o placar. |
| `ALERT_DELETE_MINUTES` | `0` | Apaga cada alerta de gol após N minutos. `0` mantém todos. |
| `DB_PATH` | `data/bot.db` | Caminho do banco de dados SQLite. |
| `DEV_GUILD_ID` | vazio | ID do servidor para registrar os comandos instantaneamente (útil em testes). |
| `PORT` | vazio | Se definida, o bot abre uma porta HTTP que responde `ok`, exigido por algumas hospedagens. |

### Ordem e ícones das competições

As competições ficam na lista `LEAGUES` em `config.py`. **A ordem da lista é a ordem dos containers no canal de partidas.** Para trocar o emblema de uma competição, adicione `"icon": "https://.../imagem.png"` na linha dela.

### Adicionar uma competição

1. Descubra o ID da liga na API-Football.
2. Acrescente uma linha em `LEAGUES` (em `config.py`):
   ```python
   135: {"name": "Serie A (Itália)", "split": True},   # split=True para temporadas europeias (2026/27)
   ```
3. Reinicie o bot e ative a competição com `/ligas`.

Competições adicionadas assim dependem apenas da API-Football e, no plano gratuito, aparecem com 1 dia de antecedência.

## Comandos

Os comandos de administração exigem a permissão **Gerenciar Servidor** (ajustável nas configurações de integrações do Discord).

| Comando | Quem usa | O que faz |
| --- | --- | --- |
| `/configurar` | Admin | Define os canais de partidas, resultados e ranking. |
| `/ligas` | Admin | Escolhe quais competições o servidor acompanha. |
| `/alertas [cargo] [sem_cargo]` | Admin | Define o cargo marcado nos alertas de gol e em quais competições eles valem. Desmarque todas para desligar. |
| `/sincronizar` | Admin | Busca jogos novos agora. Limitado a uma busca a cada 15 min para poupar a cota. |
| `/repostar [atualizar]` | Admin | Apaga e publica novamente todos os jogos futuros em `#partidas`. Com `atualizar:True`, consulta as APIs antes. |
| `/preview` | Admin | Publica jogos de exemplo (futuro, encerrado e ao vivo) para conferir o visual. |
| `/rank` | Todos | Mostra o ranking de palpites. |
| `/meuspalpites` | Todos | Lista seus últimos palpites e pontos. |

## Palpites e pontuação

| Situação | Pontos |
| --- | --- |
| Placar exato | 3 |
| Acertou só o vencedor (ou o empate) | 1 |
| Errou | 0 |

- Os palpites fecham quando o jogo começa e podem ser alterados antes disso.
- Nos mata-matas vale o placar com prorrogação, sem pênaltis.
- Desempate no ranking: pontos, depois placares exatos, depois acertos de vencedor.
- Os valores podem ser alterados em `config.py` (`PTS_EXACT` e `PTS_OUTCOME`).

## Limites dos planos gratuitos

Os planos gratuitos têm restrições que moldam o funcionamento do bot:

**API-Football (gratuito)**
- 100 requisições por dia.
- Só permite consultar **ontem, hoje e amanhã**, e não aceita consulta em lote por ID.
- Por isso, competições que só ela cobre (Libertadores, Copa do Brasil, Nations League) aparecem com até 1 dia de antecedência.

**football-data.org (gratuito)**
- Cobre Brasileirão, Premier League, La Liga, Champions e Copa do Mundo, com a agenda completa.
- O placar é atrasado e não há estatísticas detalhadas. Por isso o bot usa esta fonte só para a agenda, e a API-Football para placar ao vivo, súmula e estatísticas.

**Consumo de requisições da API-Football**
- Agenda: cerca de 16 por dia.
- Placar ao vivo: 1 requisição traz todos os jogos de uma data, então jogos simultâneos custam o mesmo que um.
- Fim de jogo: 1 requisição por jogo para súmula e estatísticas.
- Gols (se `LIVE_SCORERS=1`): 1 requisição por gol para identificar o autor.
- O intervalo entre consultas aumenta conforme a cota baixa (3, 5, 8 e 15 minutos). Com menos de 8 requisições restantes, o bot reserva o que sobrou para os resultados finais; com menos de 3, para de consultar.

Em dias com muitos jogos em horários diferentes, a cota pode apertar e os gols aparecerem com alguns minutos de atraso. Um plano pago remove essas restrições (confira os planos atuais nos sites dos provedores).

## Hospedagem

O bot precisa ficar **ligado o tempo todo** e **guardar o arquivo `data/bot.db`**, onde estão os palpites e o ranking.

Requisitos da hospedagem:
- Python 3.10+ e processo em execução contínua.
- **Disco persistente.** Plataformas que apagam o disco a cada reinício zeram o ranking, a menos que você configure um volume persistente.
- Acesso de saída HTTPS a `discord.com`, `v3.football.api-sports.io`, `media.api-sports.io` e `api.football-data.org`.
- Se a plataforma exigir uma porta aberta, defina `PORT`.

Opções comuns: máquina própria ligada 24h, mini PC/Raspberry Pi, VPS ou VM em nuvem. Termos e limites de planos gratuitos mudam com frequência, então confira as condições atuais antes de escolher.

### Exemplo: serviço systemd (Linux)

Arquivo `/etc/systemd/system/bot-futebol.service`, ajustando caminhos e usuário:

```ini
[Unit]
Description=Bot de Futebol para Discord
After=network-online.target

[Service]
User=SEU_USUARIO
WorkingDirectory=/caminho/do/projeto
ExecStart=/caminho/do/projeto/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot-futebol
journalctl -u bot-futebol -f   # acompanhar os logs
```

Faça backup periódico de `data/bot.db`.

## Solução de problemas

| Sintoma | Causa provável e solução |
| --- | --- |
| `No time zone found with key America/Brasilia` | O pacote `tzdata` não está instalado no mesmo Python que roda o bot (comum no Windows). Rode `python -m pip install -r requirements.txt`. Usar `python -m pip` garante que o pip e o Python são os mesmos. |
| `Free plans do not have access to this date` | O plano gratuito da API-Football só aceita ontem, hoje e amanhã. Mantenha `DAYS_AHEAD=1`. |
| `Free plans do not have access to this season` | O plano gratuito não permite consultas por temporada atual. O bot já evita isso; se aparecer em testes seus, consulte por data. |
| `Free plans do not have access to the Ids parameter` | Consulta em lote não existe no plano gratuito. Atualize para a versão mais recente do bot. |
| Comandos `/` não aparecem | Preencha `DEV_GUILD_ID` com o ID do servidor e reinicie. Confira se o bot foi adicionado com o escopo `applications.commands`. |
| Apaguei as mensagens e o bot não reenviou os jogos | O bot lembra o que já publicou. Use `/repostar`. |
| Escudos dos times não aparecem | Veja o log: `getaddrinfo failed` indica problema de DNS/rede ao baixar a imagem (teste `https://media.api-sports.io/football/teams/42.png` no navegador). Escudos em SVG não são suportados. Confira também a permissão de usar emojis externos para o bot. O bot tenta novamente a cada 10 minutos. |
| Aviso `PyNaCl is not installed` ou `Privileged message content intent is missing` | Podem ser ignorados: só afetam voz e comandos por prefixo, que o bot não usa. |
| Gols aparecem com atraso | Esperado no plano gratuito quando a cota diminui. Use `LIVE_LEAGUES` para limitar as competições ao vivo ou considere um plano pago. |
| Um jogo apareceu sem súmula/estatísticas | O bot não conseguiu associar o jogo entre as duas APIs. O resultado ainda é publicado, com o placar da fonte de reserva. |

## Estrutura do projeto

```
bot.py          Bot, comandos, tarefas agendadas, mensagens ao vivo e alertas
api.py          Clientes da API-Football e do football-data.org
db.py           Banco SQLite (jogos, palpites, mensagens publicadas, configurações)
embeds.py       Montagem das mensagens (containers, placar, súmula, estatísticas, ranking)
merge.py        Associa o mesmo jogo entre as duas APIs
logic.py        Pontuação, status de jogo e intervalo adaptativo
config.py       Opções, competições e pontuação
check_api.py    Teste rápido da chave da API-Football
```

## Limitações conhecidas e planos futuros

- Os nomes dos times vêm da API (alguns em inglês) e podem diferir entre as fontes.
- O estádio nem sempre está disponível para jogos distantes; passa a aparecer quando o jogo entra na janela da API-Football.
- Se o bot for iniciado no meio de um jogo, ele não alerta os gols anteriores.
- A ordem de quem entra e quem sai nas substituições da súmula segue a interpretação da documentação da API; se aparecer invertida, ajuste em `embeds.py`.
- **Planejado:** suporte a e-sports (por exemplo, Rainbow Six), com fonte de dados a definir.

Sugestões e correções são bem-vindas por issues e pull requests.

## Privacidade e licença

O bot armazena localmente, em `data/bot.db`, apenas os IDs de usuário do Discord, os palpites e as configurações do servidor. Ele não lê o conteúdo das mensagens dos membros.

Escudos e emblemas pertencem aos respectivos clubes e competições; os dados pertencem aos provedores, e o uso deles está sujeito aos termos de cada API.

Este projeto ainda não define uma licença. Até que um arquivo `LICENSE` seja adicionado, todos os direitos permanecem reservados ao autor.