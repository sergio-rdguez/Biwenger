---
name: biwenger-api
description: >-
  Documenta la API no oficial de Biwenger usada por sync_biwenger.py: login,
  league standings, rounds live, board roundFinished/roundStarted, aliases y
  estados final/provisional/prematch. Use when changing sync, debugging API,
  jornada status, or manager name mapping.
---

# Biwenger API (sync)

## Auth

- `POST https://biwenger.as.com/api/v2/auth/login` body `{email, password}` → `token`
- Headers siguientes: `Authorization: Bearer …`, `X-League`, `X-User`, `X-Lang: es`
- Cuenta/liga: `GET /api/v2/account` (elige liga por `BIWENGER_LEAGUE` o la primera)

## Endpoints clave

| Uso | URL |
|-----|-----|
| Clasificación temporada | `GET /api/v2/league?include=all&fields=*,standings,…` |
| Ranking jornada en curso | `GET /api/v2/rounds/league` |
| Tablón | `GET /api/v2/league/{id}/board?offset=&limit=` |
| Catálogo jugadores | `GET /api/v2/competitions/la-liga/data?lang=es&score=5` |
| Mercado | `GET /api/v2/market` |
| Detalle manager | `GET /api/v2/user/{id}?fields=name,balance,points,players(id,owner),lineups…` |

Feed ampliado en `biwenger_feed.py` → `enrich_league_feed()` (mercado, actividad, fixtures, once, plantillas).

Puntos de jornada por jugador: `fitness[]` del catálogo va **de más reciente a más antigua**
(`fitness[0]` = jornada activa / última puntuada). Offset = `current_jornada - jornada`.

## Estados de jornada

Implementados en `sync_biwenger.py`:

| Status | Significado | Suma al bote |
|--------|-------------|--------------|
| `final` | Evento `roundFinished` en tablón | Sí (oficial) |
| `provisional` | Jornada activa con puntos de once (`fitness` del catálogo) o live distinto | Sí (estimado) |
| `prematch` | Jornada abierta pero sin puntos de once todavía; live espeja la final anterior | **No** |

Fuente de verdad de calendarios: `competitions/la-liga/data` → `season.rounds`
(`finished` / `active` / `pending`, incl. jornadas aplazadas `part: 2`).

El tablón se filtra a los `round.id` de la temporada actual (evita mezclar temporadas viejas).

Si `/rounds/league` sigue mostrando puntos de la jornada anterior, el ranking provisional
se calcula sumando `fitness[0]` (jornada activa) de cada titular del once.

`postponed_rounds` lista aplazadas pendientes (p.ej. «Jornada 1 (aplazada)»).

El `round.id` actual se mapea a número vía `roundStarted`/`roundFinished` (`name`: "Jornada N").

`standings[].lastPositions` **no** se usa para el ranking de jornada: el índice
`i → jornada i+1` falla cuando Biwenger cierra jornadas fuera de orden (p.ej. J6
antes que J5) y corrompe puestos/bote. Fuente de verdad = tablón.

Para jornadas cerradas:

- Usa `roundFinished.results` para puntos, premio (`bonus`) y puesto (ordenar por
  puntos; el evento suele no traer `position` explícita).
- Conserva `round_id`, `started_at` y `finished_at` en `rounds_meta`.

## Aliases

Archivo: `data/aliases.json`

```json
{ "aliases": { "Nombre Biwenger exacto": "NombreWeb" } }
```

El sync **solo** acepta managers ya en la plantilla canónica (salvo plantilla vacía). Sin alias → se omite el remoto.

## Modelo JSON (campos importantes)

```text
season, pot_rules, previous_season
current_jornada, current_round_status, rounds_meta
classification[]  # puesto, pts, team_value, …
market { sales[], offers[], viewer_balance, viewer_max_bid }
activity { transfers[], market_deals[], clause_increments[] }
fixtures[]  # partidos de la jornada actual (atajo)
fixtures_by_round { "N": [partidos...] }  # resultados/calendario por jornada
players_index { id: {name, team, position_label, points_last, …} }
players[]:
  name, positions, rounds{ j: {position,status,points,bonus,round_id} }
  points, team_value, team_value_inc, team_size, formation,
  last_access, season_position, balance, max_bid,
  lineup { formation, starters[], bench[], points_sum },
  roster[{ id, name, clause, in_xi, points_last, … }]
```

## Al evolucionar el sync

1. Mantener escritura dual: `data/liga.json` + `web/data/liga.json`
2. Preservar `previous_season`
3. Actualizar UI si hay campos nuevos → skill `evolve-web`
4. Actualizar esta skill si cambian endpoints o semántica
