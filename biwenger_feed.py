"""Extra Biwenger feed: market, activity, rosters, fixtures, player points."""

from __future__ import annotations

import re
import time
from typing import Any

import requests

CATALOG_URL = (
    "https://biwenger.as.com/api/v2/competitions/la-liga/data?lang=es&score=5"
)
MARKET_URL = "https://biwenger.as.com/api/v2/market"
USER_URL = (
    "https://biwenger.as.com/api/v2/user/{user_id}"
    "?fields=name,balance,points,players(id,owner),"
    "lineups(round,points,count,position,type,date,players)"
)

POS_LABEL = {1: "PT", 2: "DF", 3: "MC", 4: "DL"}


def last_fitness_points(fitness: Any) -> int | None:
    """Puntos de la jornada más reciente.

    En Biwenger, `fitness` va de más reciente a más antigua:
    fitness[0] = jornada activa / última puntuada, fitness[1] = anterior, …
    """
    if not isinstance(fitness, list) or not fitness:
        return None
    value = fitness[0]
    if isinstance(value, (int, float)):
        return int(value)
    return None


def fitness_for_jornada(
    fitness: Any,
    jornada: int | None,
    current_jornada: int | None,
) -> int | None:
    """Puntos de un jugador en una jornada concreta (fitness newest-first)."""
    if not isinstance(fitness, list) or jornada is None or current_jornada is None:
        return None
    offset = int(current_jornada) - int(jornada)
    if offset < 0 or offset >= len(fitness):
        return None
    value = fitness[offset]
    if isinstance(value, (int, float)):
        return int(value)
    return None


def fetch_competition_meta(session: requests.Session) -> dict:
    """Season rounds + raw catalog players (for gameweek points)."""
    res = session.get(CATALOG_URL, timeout=60)
    res.raise_for_status()
    data = res.json().get("data") or {}
    season = data.get("season") or {}
    return {
        "season_rounds": season.get("rounds") or [],
        "players": data.get("players") or {},
        "teams": {str(k): v for k, v in (data.get("teams") or {}).items()},
        "active_events": data.get("activeEvents") or [],
    }


def lineup_gameweek_points(
    lineup: dict | None,
    catalog_players: dict,
    *,
    jornada: int | None = None,
    current_jornada: int | None = None,
) -> int | None:
    """Suma puntos de jornada del once (fitness newest-first)."""
    if not isinstance(lineup, dict):
        return None
    target = jornada if jornada is not None else current_jornada
    total = 0
    scored = 0
    for pid in lineup.get("players") or []:
        if pid is None:
            continue
        raw = catalog_players.get(str(pid)) or {}
        if target is not None and current_jornada is not None:
            pts = fitness_for_jornada(raw.get("fitness"), target, current_jornada)
        else:
            pts = last_fitness_points(raw.get("fitness"))
        if pts is None:
            continue
        total += pts
        scored += 1
    return total if scored else None


def active_season_round(season_rounds: list[dict]) -> dict | None:
    for row in season_rounds:
        if row.get("status") == "active" and not row.get("part"):
            return row
    return None


def pending_postponed_rounds(season_rounds: list[dict]) -> list[dict]:
    out = []
    for row in season_rounds:
        if row.get("status") == "pending" and row.get("part"):
            out.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "short": row.get("short"),
                    "part": row.get("part"),
                    "status": row.get("status"),
                }
            )
    return out


def season_round_ids(season_rounds: list[dict]) -> set[int]:
    ids: set[int] = set()
    for row in season_rounds:
        rid = row.get("id")
        if rid is not None:
            ids.add(int(rid))
    return ids


def fetch_catalog(session: requests.Session) -> tuple[dict[str, dict], dict[str, dict]]:
    res = session.get(CATALOG_URL, timeout=60)
    res.raise_for_status()
    data = res.json().get("data") or {}
    players = data.get("players") or {}
    teams = {str(k): v for k, v in (data.get("teams") or {}).items()}
    return players, teams


def slim_player(pid: int | str | None, catalog: dict[str, dict], teams: dict[str, dict]) -> dict:
    if pid is None:
        return {
            "id": None,
            "name": "?",
            "position": None,
            "position_label": "?",
            "price": None,
            "points": None,
            "points_last": None,
            "fitness": [],
            "status": None,
            "team": None,
            "team_id": None,
        }
    raw = catalog.get(str(pid)) or {}
    team_id = raw.get("teamID") or raw.get("teamId") or raw.get("team")
    if isinstance(team_id, dict):
        team_id = team_id.get("id")
    team = teams.get(str(team_id)) or {}
    return {
        "id": int(pid),
        "name": raw.get("name") or f"#{pid}",
        "position": raw.get("position"),
        "position_label": POS_LABEL.get(raw.get("position"), "?"),
        "price": raw.get("price"),
        "points": raw.get("points"),
        "points_last": last_fitness_points(raw.get("fitness")),
        "fitness": raw.get("fitness") if isinstance(raw.get("fitness"), list) else [],
        "status": raw.get("status"),
        "team": team.get("name") or team.get("slug"),
        "team_id": int(team_id) if team_id is not None else None,
    }


def collect_ids(*groups) -> set[int]:
    ids: set[int] = set()
    for group in groups:
        for item in group or []:
            if isinstance(item, int):
                ids.add(item)
            elif isinstance(item, dict) and item.get("player") is not None:
                try:
                    ids.add(int(item["player"]))
                except (TypeError, ValueError):
                    pass
            elif isinstance(item, dict) and item.get("id") is not None:
                try:
                    ids.add(int(item["id"]))
                except (TypeError, ValueError):
                    pass
    return ids


def _game_from_pool_row(game: dict) -> dict | None:
    gid = game.get("id")
    if gid is None:
        return None
    home = game.get("home") or {}
    away = game.get("away") or {}
    return {
        "id": gid,
        "date": game.get("date"),
        "status": game.get("status"),
        "home": home.get("name"),
        "away": away.get("name"),
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "home_difficulty": (home.get("difficulty") or {}).get("rating"),
        "away_difficulty": (away.get("difficulty") or {}).get("rating"),
    }


def _prefer_game(prev: dict | None, cand: dict) -> dict:
    if not prev:
        return cand
    if prev.get("status") != "finished" and cand.get("status") == "finished":
        return cand
    if prev.get("home_score") is None and cand.get("home_score") is not None:
        return cand
    # Keep richer difficulty when scores already present
    if cand.get("home_difficulty") is not None and prev.get("home_difficulty") is None:
        merged = dict(prev)
        merged["home_difficulty"] = cand.get("home_difficulty")
        merged["away_difficulty"] = cand.get("away_difficulty")
        return merged
    return prev


def collect_board_games(board: list[dict], *, min_event_date: int | None = None) -> dict[int, dict]:
    """Deduped match rows from bettingPool board events (id -> game)."""
    games: dict[int, dict] = {}
    for event in board:
        if event.get("type") != "bettingPool":
            continue
        if min_event_date is not None and (event.get("date") or 0) < min_event_date:
            continue
        content = event.get("content")
        if not isinstance(content, dict):
            continue
        pool = content.get("pool") or {}
        for row in pool.get("games") or []:
            cand = _game_from_pool_row(row)
            if not cand:
                continue
            gid = int(cand["id"])
            games[gid] = _prefer_game(games.get(gid), cand)
    return games


def collect_active_event_games(active_events: list[dict] | None) -> dict[int, dict]:
    games: dict[int, dict] = {}
    for ev in active_events or []:
        for row in ev.get("games") or []:
            cand = _game_from_pool_row(row)
            if not cand:
                continue
            gid = int(cand["id"])
            games[gid] = _prefer_game(games.get(gid), cand)
    return games


def _extract_round_number(name: str | None) -> int | None:
    if not isinstance(name, str):
        return None
    m = re.search(r"(\d+)", name)
    return int(m.group(1)) if m else None


def build_fixture_windows(
    rounds_meta: dict,
    active_events: list[dict] | None = None,
) -> list[dict]:
    """Time windows used to assign matches to jornada numbers."""
    windows: list[dict] = []
    for key, meta in (rounds_meta or {}).items():
        start = meta.get("started_at")
        if start is None:
            continue
        end = meta.get("finished_at")
        windows.append(
            {
                "number": int(meta.get("number") or key),
                "start": int(start),
                "end": int(end) if end is not None else int(start) + 8 * 86400,
            }
        )
    known = {w["number"] for w in windows}
    for ev in active_events or []:
        if ev.get("type") and ev.get("type") != "round":
            continue
        num = _extract_round_number(ev.get("name") or ev.get("short"))
        if num is None or num in known:
            continue
        start = ev.get("start") or ev.get("date")
        if start is None:
            continue
        end = ev.get("end") or start
        windows.append(
            {
                "number": num,
                "start": int(start),
                "end": int(end) + 7 * 86400,
            }
        )
        known.add(num)
    windows.sort(key=lambda w: w["start"])
    return windows


def assign_game_to_jornada(game_date: int | None, windows: list[dict]) -> int | None:
    if game_date is None or not windows:
        return None
    hits = [w for w in windows if w["start"] <= game_date <= w["end"]]
    if len(hits) == 1:
        return hits[0]["number"]
    if len(hits) > 1:
        hits.sort(key=lambda w: w["end"] - w["start"])
        return hits[0]["number"]
    prev = [w for w in windows if w["start"] <= game_date]
    if prev:
        return prev[-1]["number"]
    return windows[0]["number"]


def build_fixtures_by_round(
    board: list[dict],
    rounds_meta: dict,
    *,
    active_events: list[dict] | None = None,
    min_event_date: int | None = None,
) -> dict[str, list[dict]]:
    """Group La Liga matches by jornada using board pools + activeEvents."""
    games = collect_board_games(board, min_event_date=min_event_date)
    for gid, game in collect_active_event_games(active_events).items():
        games[gid] = _prefer_game(games.get(gid), game)

    windows = build_fixture_windows(rounds_meta, active_events)
    by_round: dict[str, list[dict]] = {}
    for game in games.values():
        jornada = assign_game_to_jornada(game.get("date"), windows)
        if jornada is None:
            continue
        row = dict(game)
        row["jornada"] = jornada
        by_round.setdefault(str(jornada), []).append(row)

    for key in by_round:
        by_round[key].sort(key=lambda g: (g.get("date") or 0, g.get("id") or 0))
    return by_round


def parse_board_activity(board: list[dict], limit: int = 40) -> dict:
    transfers: list[dict] = []
    market_deals: list[dict] = []
    clauses: list[dict] = []
    fixtures: list[dict] = []

    for event in board:
        typ = event.get("type")
        content = event.get("content")
        date = event.get("date")

        # Legacy: first (newest) bettingPool only — callers prefer fixtures_by_round.
        if typ == "bettingPool" and isinstance(content, dict) and not fixtures:
            pool = content.get("pool") or {}
            for game in pool.get("games") or []:
                row = _game_from_pool_row(game)
                if row:
                    fixtures.append(row)

        if not isinstance(content, list):
            continue

        if typ == "transfer" and len(transfers) < limit:
            for row in content:
                transfers.append(
                    {
                        "date": date,
                        "player_id": row.get("player"),
                        "amount": row.get("amount"),
                        "from": (row.get("from") or {}).get("name"),
                        "from_id": (row.get("from") or {}).get("id"),
                        "to": (row.get("to") or {}).get("name") if row.get("to") else None,
                        "to_id": (row.get("to") or {}).get("id") if row.get("to") else None,
                        "kind": "clausulazo" if row.get("from") and not row.get("to") else "transfer",
                    }
                )
                # Biwenger clausulazo often only has "from" (seller) — buyer may be elsewhere
                # Actually sample showed only from+amount. Check again - clausulazo might be
                # from = previous owner. Need "to" for buyer. Looking at sample_transfer:
                # only from. Hmm. Maybe admin or different structure.
                # For market type we have "to".

        if typ == "market" and len(market_deals) < limit:
            for row in content:
                bids = [
                    {
                        "manager": (b.get("user") or {}).get("name"),
                        "manager_id": (b.get("user") or {}).get("id"),
                        "amount": b.get("amount"),
                    }
                    for b in (row.get("bids") or [])
                ]
                market_deals.append(
                    {
                        "date": date,
                        "player_id": row.get("player"),
                        "amount": row.get("amount"),
                        "to": (row.get("to") or {}).get("name"),
                        "to_id": (row.get("to") or {}).get("id"),
                        "from": (row.get("from") or {}).get("name") if row.get("from") else None,
                        "bids": bids,
                    }
                )

        if typ == "clauseIncrement" and len(clauses) < limit:
            for row in content:
                clauses.append(
                    {
                        "date": date,
                        "player_id": row.get("player"),
                        "manager": (row.get("user") or {}).get("name"),
                        "manager_id": (row.get("user") or {}).get("id"),
                        "amount": row.get("amount"),
                        "release_clause": row.get("releaseClause"),
                    }
                )

        if (
            len(transfers) >= limit
            and len(market_deals) >= limit
            and len(clauses) >= limit
            and fixtures
        ):
            break

    return {
        "transfers": transfers[:limit],
        "market_deals": market_deals[:limit],
        "clause_increments": clauses[:limit],
        "fixtures": fixtures,
    }


def fetch_market(session: requests.Session) -> dict:
    res = session.get(MARKET_URL, timeout=30)
    res.raise_for_status()
    data = res.json().get("data") or {}
    status = data.get("status") or {}
    sales = []
    for row in data.get("sales") or []:
        sales.append(
            {
                "player_id": row.get("player") if not isinstance(row.get("player"), dict) else row["player"].get("id"),
                "price": row.get("price"),
                "date": row.get("date"),
                "until": row.get("until"),
                "seller": (row.get("user") or {}).get("name"),
                "seller_id": (row.get("user") or {}).get("id"),
            }
        )
    # player may be int id
    for row in sales:
        if isinstance(row["player_id"], dict):
            row["player_id"] = row["player_id"].get("id")
    offers = []
    for row in data.get("offers") or []:
        offers.append(
            {
                "type": row.get("type"),
                "amount": row.get("amount"),
                "until": row.get("until"),
                "player_id": row.get("requestedPlayers", [None])[0]
                if isinstance(row.get("requestedPlayers"), list)
                else row.get("player"),
                "from_id": row.get("fromID") or (row.get("from") or {}).get("id"),
            }
        )
    return {
        "sales": sales,
        "offers": offers,
        "viewer_balance": status.get("balance"),
        "viewer_max_bid": status.get("maximumBid"),
    }


def fetch_user_detail(session: requests.Session, user_id: int) -> dict:
    res = session.get(USER_URL.format(user_id=user_id), timeout=30)
    if res.status_code != 200:
        return {}
    return res.json().get("data") or {}


def extract_round_number(round_obj: dict | None) -> int | None:
    if not isinstance(round_obj, dict):
        return None
    name = round_obj.get("name") or round_obj.get("short") or ""
    if isinstance(name, str):
        m = re.search(r"(\d+)", name)
        if m:
            return int(m.group(1))
    short = round_obj.get("shortName")
    if isinstance(short, int):
        return short
    return None


def build_lineup_detail(
    lineup: dict | None,
    catalog: dict[str, dict],
    teams: dict[str, dict],
    jornada: int | None = None,
    current_jornada: int | None = None,
) -> dict | None:
    if not isinstance(lineup, dict):
        return None
    ref_current = current_jornada if current_jornada is not None else jornada
    starters = []
    for pid in lineup.get("players") or []:
        if pid is None:
            continue
        info = slim_player(pid, catalog, teams)
        if jornada is not None:
            info["points_jornada"] = fitness_for_jornada(
                info.get("fitness"), jornada, ref_current
            )
        else:
            info["points_jornada"] = info.get("points_last")
        starters.append(info)
    bench = []
    for pid in lineup.get("discarded") or []:
        if pid is None:
            continue
        info = slim_player(pid, catalog, teams)
        if jornada is not None:
            info["points_jornada"] = fitness_for_jornada(
                info.get("fitness"), jornada, ref_current
            )
        else:
            info["points_jornada"] = info.get("points_last")
        bench.append(info)
    scored = sum(p["points_jornada"] or 0 for p in starters)
    return {
        "formation": lineup.get("type"),
        "counting": lineup.get("count"),
        "updated_at": lineup.get("date"),
        "starters": starters,
        "bench": bench,
        "points_sum": scored,
    }


def build_lineup_from_history(
    entry: dict,
    catalog: dict[str, dict],
    teams: dict[str, dict],
    current_jornada: int | None = None,
) -> dict | None:
    rnd = entry.get("round") or {}
    jornada = extract_round_number(rnd)
    if jornada is None:
        return None
    ref_current = current_jornada if current_jornada is not None else jornada
    starters = []
    for row in entry.get("players") or []:
        if isinstance(row, dict):
            pid = row.get("id")
            if pid is None:
                continue
            info = slim_player(pid, catalog, teams)
            if row.get("name"):
                info["name"] = row["name"]
            team = row.get("team")
            if isinstance(team, dict) and team.get("name"):
                info["team"] = team["name"]
            pos = row.get("position")
            if pos is not None:
                info["position"] = pos
                info["position_label"] = POS_LABEL.get(pos, info.get("position_label"))
            fit = row.get("fitness") if isinstance(row.get("fitness"), list) else info.get("fitness")
            info["points_jornada"] = fitness_for_jornada(fit, jornada, ref_current)
        else:
            info = slim_player(row, catalog, teams)
            info["points_jornada"] = fitness_for_jornada(
                info.get("fitness"), jornada, ref_current
            )
        starters.append(info)
    official = entry.get("points")
    return {
        "formation": entry.get("type"),
        "counting": entry.get("count"),
        "updated_at": entry.get("date"),
        "round_id": rnd.get("id"),
        "jornada": jornada,
        "league_position": entry.get("position"),
        "starters": starters,
        "bench": [],
        "points_sum": official
        if official is not None
        else sum(p.get("points_jornada") or 0 for p in starters),
    }


def slim_lineup_public(lineup: dict | None) -> dict | None:
    """Drop heavy fields before writing liga.json."""
    if not isinstance(lineup, dict):
        return None
    return {
        "formation": lineup.get("formation"),
        "counting": lineup.get("counting"),
        "updated_at": lineup.get("updated_at"),
        "round_id": lineup.get("round_id"),
        "league_position": lineup.get("league_position"),
        "points_sum": lineup.get("points_sum"),
        "starters": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "position_label": p.get("position_label"),
                "team": p.get("team"),
                "points_jornada": p.get("points_jornada"),
                "price": p.get("price"),
            }
            for p in (lineup.get("starters") or [])
        ],
        "bench": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "position_label": p.get("position_label"),
                "team": p.get("team"),
                "points_jornada": p.get("points_jornada"),
                "price": p.get("price"),
            }
            for p in (lineup.get("bench") or [])
        ],
    }


def build_lineups_by_round(
    history: list,
    catalog: dict[str, dict],
    teams: dict[str, dict],
    current_jornada: int | None = None,
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        detail = build_lineup_from_history(
            entry, catalog, teams, current_jornada=current_jornada
        )
        if not detail or detail.get("jornada") is None:
            continue
        public = slim_lineup_public(detail)
        if public:
            out[str(detail["jornada"])] = public
    return out


def build_roster(
    user_data: dict,
    catalog: dict[str, dict],
    teams: dict[str, dict],
    lineup_ids: set[int],
    bench_ids: set[int],
) -> list[dict]:
    roster = []
    for row in user_data.get("players") or []:
        pid = row.get("id")
        if pid is None:
            continue
        owner = row.get("owner") or {}
        info = slim_player(pid, catalog, teams)
        info.update(
            {
                "clause": owner.get("clause"),
                "bought_price": owner.get("price"),
                "owned_since": owner.get("date"),
                "in_xi": int(pid) in lineup_ids,
                "on_bench": int(pid) in bench_ids,
            }
        )
        roster.append(info)
    roster.sort(
        key=lambda p: (
            0 if p.get("in_xi") else 1 if p.get("on_bench") else 2,
            p.get("position") or 9,
            -(p.get("points") or 0),
        )
    )
    return roster


def enrich_league_feed(
    session: requests.Session,
    *,
    aliases: dict[str, str],
    normalize_name,
    by_name: dict[str, dict],
    standings: list[dict],
    live_standings: list[dict],
    board: list[dict],
    accept_all_new: bool,
    catalog: dict[str, dict] | None = None,
    teams: dict[str, dict] | None = None,
    current_jornada: int | None = None,
) -> dict:
    print("Descargando mercado y plantillas…")
    if catalog is None or teams is None:
        catalog, teams = fetch_catalog(session)
    market = fetch_market(session)
    activity = parse_board_activity(board)
    live_by_id = {row.get("id"): row for row in live_standings}

    used_ids: set[int] = set()
    managers_extra: dict[str, dict] = {}

    for row in standings:
        remote_name = (row.get("name") or "").strip()
        web_name = normalize_name(remote_name, aliases)
        if web_name.lower() == "bonilla":
            continue
        if not accept_all_new and web_name not in by_name:
            continue
        user_id = row.get("id")
        detail = fetch_user_detail(session, int(user_id))
        time.sleep(0.05)
        live = live_by_id.get(user_id) or {}
        lineup = live.get("lineup") if isinstance(live.get("lineup"), dict) else {}
        starter_ids = {int(x) for x in (lineup.get("players") or []) if x is not None}
        bench_ids = {int(x) for x in (lineup.get("discarded") or []) if x is not None}
        history = detail.get("lineups") or []
        lineups_by_round = build_lineups_by_round(
            history, catalog, teams, current_jornada=current_jornada
        )
        live_detail = slim_lineup_public(
            build_lineup_detail(
                lineup,
                catalog,
                teams,
                jornada=current_jornada,
                current_jornada=current_jornada,
            )
        )
        if (
            current_jornada
            and live_detail
            and live_detail.get("starters")
            and str(current_jornada) not in lineups_by_round
        ):
            lineups_by_round[str(current_jornada)] = live_detail
        roster = build_roster(detail, catalog, teams, starter_ids, bench_ids)
        # Slim roster for public JSON
        roster_public = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "position_label": p.get("position_label"),
                "team": p.get("team"),
                "points": p.get("points"),
                "points_last": p.get("points_last"),
                "price": p.get("price"),
                "clause": p.get("clause"),
                "in_xi": p.get("in_xi"),
                "on_bench": p.get("on_bench"),
            }
            for p in roster
        ]
        used_ids |= starter_ids | bench_ids
        used_ids |= {int(p["id"]) for p in roster if p.get("id") is not None}
        for lu in lineups_by_round.values():
            for p in lu.get("starters") or []:
                if p.get("id") is not None:
                    used_ids.add(int(p["id"]))

        balance = detail.get("balance")
        team_value = int(row.get("teamValue") or 0)
        max_bid = None
        if isinstance(balance, (int, float)):
            max_bid = int(balance + team_value / 4)

        managers_extra[web_name] = {
            "balance": balance,
            "max_bid": max_bid,
            "lineup": live_detail,
            "roster": roster_public,
            "lineups_by_round": lineups_by_round,
        }

        player = by_name.get(web_name)
        if player is not None:
            player["balance"] = balance
            player["max_bid"] = max_bid
            player["lineup"] = live_detail
            player["roster"] = roster_public
            player["lineups_by_round"] = lineups_by_round

    # Enrich market/activity with names
    for sale in market.get("sales") or []:
        pid = sale.get("player_id")
        if pid is not None:
            used_ids.add(int(pid))
            info = slim_player(pid, catalog, teams)
            sale["player"] = info["name"]
            sale["position_label"] = info["position_label"]
            sale["team"] = info["team"]
            sale["points_last"] = info["points_last"]

    for bucket in ("transfers", "market_deals", "clause_increments"):
        for row in activity.get(bucket) or []:
            pid = row.get("player_id")
            if pid is None:
                continue
            used_ids.add(int(pid))
            info = slim_player(pid, catalog, teams)
            row["player"] = info["name"]
            row["position_label"] = info["position_label"]
            row["team"] = info["team"]

    players_index = {
        str(pid): slim_player(pid, catalog, teams) for pid in sorted(used_ids)
    }

    # Fix transfer direction: in Biwenger, transfer content with only "from"
    # is often the seller when clause is paid; look for paired events is hard.
    # Keep as-is; UI will show "sale de X por importe".

    return {
        "market": market,
        "activity": activity,
        "fixtures": activity.get("fixtures") or [],
        "players_index": players_index,
        "managers_extra": managers_extra,
    }
