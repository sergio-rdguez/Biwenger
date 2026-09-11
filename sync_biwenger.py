#!/usr/bin/env python3
"""Sincroniza clasificación, jornadas (provisionales/finales) y bote desde Biwenger."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "liga.json"
WEB_DATA_PATH = ROOT / "web" / "data" / "liga.json"
ALIASES_PATH = ROOT / "data" / "aliases.json"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LOGIN_URL = "https://biwenger.as.com/api/v2/auth/login"
ACCOUNT_URL = "https://biwenger.as.com/api/v2/account"
LEAGUE_DETAIL_URL = (
    "https://biwenger.as.com/api/v2/league"
    "?include=all&fields=*,standings,group,settings(description)"
)
ROUNDS_URL = "https://biwenger.as.com/api/v2/rounds/league"
BOARD_URL = "https://biwenger.as.com/api/v2/league/{league_id}/board"

from biwenger_feed import (
    active_season_round,
    build_fixtures_by_round,
    enrich_league_feed,
    fetch_competition_meta,
    lineup_gameweek_points,
    pending_postponed_rounds,
    season_round_ids,
)

DEFAULT_POT = {"8": 0.5, "9": 1.0, "10": 1.5, "11": 2.0, "12": 2.5}

HEADERS_BASE = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "X-Lang": "es",
}


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_env_aliases() -> dict[str, str]:
    raw = os.getenv("BIWENGER_ALIASES", "").strip()
    if not raw:
        return {}
    out: dict[str, str] = {}
    for part in raw.split(","):
        if "=" not in part:
            continue
        src, dst = part.split("=", 1)
        out[src.strip()] = dst.strip()
    return out


def load_aliases() -> dict[str, str]:
    file_aliases = load_json(ALIASES_PATH, {}).get("aliases", {})
    return {**file_aliases, **parse_env_aliases()}


def normalize_name(name: str, aliases: dict[str, str]) -> str:
    name = (name or "").strip()
    return aliases.get(name, name)


def login(email: str, password: str) -> str:
    res = requests.post(
        LOGIN_URL,
        headers=HEADERS_BASE,
        json={"email": email, "password": password},
        timeout=30,
    )
    res.raise_for_status()
    payload = res.json()
    token = payload.get("token")
    if not token:
        raise RuntimeError(f"Login fallido: {payload}")
    return token


def get_account_league(session: requests.Session) -> dict:
    res = session.get(ACCOUNT_URL, timeout=30)
    res.raise_for_status()
    data = res.json().get("data") or {}
    leagues = data.get("leagues") or []
    if not leagues:
        raise RuntimeError("La cuenta no tiene ligas.")
    wanted = (os.getenv("BIWENGER_LEAGUE") or "").strip().lower()
    if wanted:
        for league in leagues:
            if (league.get("name") or "").strip().lower() == wanted:
                return league
        names = ", ".join(l.get("name", "?") for l in leagues)
        raise RuntimeError(f'No se encontró la liga "{wanted}". Disponibles: {names}')
    return leagues[0]


def build_session(token: str, league: dict) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            **HEADERS_BASE,
            "Authorization": f"Bearer {token}",
            "X-League": str(league["id"]),
            "X-User": str(league["user"]["id"]),
        }
    )
    return session


def fetch_board(session: requests.Session, league_id: int) -> list[dict]:
    items: list[dict] = []
    offset = 0
    limit = 100
    while True:
        url = BOARD_URL.format(league_id=league_id)
        res = session.get(url, params={"offset": offset, "limit": limit}, timeout=30)
        res.raise_for_status()
        chunk = res.json().get("data") or []
        if not chunk:
            break
        items.extend(chunk)
        if len(chunk) < limit:
            break
        offset += limit
        if offset > 3000:
            break
    return items


def extract_jornada_number(round_obj: dict) -> int | None:
    if not round_obj:
        return None
    if isinstance(round_obj.get("name"), str):
        m = re.search(r"(\d+)", round_obj["name"])
        if m:
            return int(m.group(1))
    val = round_obj.get("shortName")
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return None


def board_rounds(board: list[dict], allowed_ids: set[int] | None = None) -> dict[int, dict]:
    """round_id -> metadata and final results.

    If allowed_ids is set, ignore board events from other seasons.
    """
    by_id: dict[int, dict] = {}
    for event in board:
        content = event.get("content")
        if not isinstance(content, dict):
            continue
        round_obj = content.get("round")
        if not isinstance(round_obj, dict):
            continue
        rid = round_obj.get("id")
        num = extract_jornada_number(round_obj)
        if rid is None or num is None:
            continue
        rid = int(rid)
        if allowed_ids is not None and rid not in allowed_ids:
            continue
        # Skip postponed parts as separate jornada numbers (e.g. J1 aplazada)
        if round_obj.get("part"):
            continue
        entry = by_id.setdefault(
            rid,
            {
                "number": num,
                "round_id": rid,
                "started_at": None,
                "finished_at": None,
                "finished": False,
                "results": None,
            },
        )
        entry["number"] = num
        if event.get("type") == "roundStarted":
            entry["started_at"] = event.get("date")
        elif event.get("type") == "roundFinished":
            entry["finished"] = True
            entry["finished_at"] = event.get("date")
            results = content.get("results")
            entry["results"] = results if isinstance(results, list) else []
    return by_id


def rank_results(results: list[dict]) -> list[dict]:
    """Normalize final board results while preserving Biwenger's order."""
    scored = []
    for idx, row in enumerate(results or []):
        user = row.get("user") or {}
        name = (user.get("name") or "").strip()
        if not name:
            continue
        scored.append(
            {
                "name": name,
                "points": int(row.get("points") or 0),
                "explicit": row.get("position")
                if isinstance(row.get("position"), int)
                else None,
                "idx": idx,
                "bonus": int(row.get("bonus") or 0),
                "reason": row.get("reason"),
            }
        )
    if any(s["explicit"] is not None for s in scored):
        scored.sort(
            key=lambda s: (s["explicit"] is None, s["explicit"] or 999, -s["points"], s["idx"])
        )
    else:
        scored.sort(key=lambda s: (-s["points"], s["idx"]))
    for fallback_position, result in enumerate(scored, start=1):
        result["position"] = result["explicit"] or fallback_position
    return scored


def set_round(
    player: dict,
    jornada: int,
    position: int,
    status: str,
    points: int | None = None,
    **extra,
) -> None:
    player["positions"][str(jornada)] = int(position)
    player["rounds"][str(jornada)] = {
        "position": int(position),
        "status": status,
        "points": points,
        **{key: value for key, value in extra.items() if value is not None},
    }


def is_mirrored_prematch(
    live_rows: list[tuple[str, int, int | None]],
    players_by_name: dict[str, dict],
    previous_jornada: int,
    finished_jornadas: set[int],
) -> bool:
    """True when the live endpoint still mirrors the previous final round."""
    if not live_rows or previous_jornada not in finished_jornadas:
        return False
    for name, _position, points in live_rows:
        previous = (
            players_by_name.get(name, {}).get("rounds", {}).get(str(previous_jornada))
        )
        if (
            not previous
            or previous.get("status") != "final"
            or previous.get("points") != points
        ):
            return False
    return True


def is_mirrored_gameweek_points(
    gw_rows: list[tuple[str, int]],
    players_by_name: dict[str, dict],
    previous_jornada: int,
    finished_jornadas: set[int],
) -> bool:
    """True when fitness[0] still equals the previous final jornada points."""
    if not gw_rows or previous_jornada not in finished_jornadas:
        return False
    for name, points in gw_rows:
        previous = (
            players_by_name.get(name, {}).get("rounds", {}).get(str(previous_jornada))
        )
        if (
            not previous
            or previous.get("status") != "final"
            or previous.get("points") != points
        ):
            return False
    return True

def sync(dry_run: bool = False) -> dict:
    email = os.getenv("BIWENGER_EMAIL") or os.getenv("BIWENGER_USERNAME")
    password = os.getenv("BIWENGER_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Faltan BIWENGER_EMAIL y BIWENGER_PASSWORD. Copia .env.example a .env"
        )

    aliases = load_aliases()
    empty_state = {
        "league_name": "Liga Biwenger",
        "season": "2026-2027",
        "pot_rules": DEFAULT_POT,
        "jornadas": 38,
        "players": [],
    }
    # Si data/liga.json falta o está vacío, cae a la copia pública antes de
    # tratar a todos los managers como nuevos (evita perder aliases curados).
    if DATA_PATH.exists():
        current = load_json(DATA_PATH, empty_state)
    else:
        current = load_json(WEB_DATA_PATH, empty_state)

    print("Autenticando en Biwenger…")
    token = login(email, password)
    tmp = requests.Session()
    tmp.headers.update({**HEADERS_BASE, "Authorization": f"Bearer {token}"})
    league = get_account_league(tmp)
    print(f"Liga: {league.get('name')} (id={league.get('id')})")

    session = build_session(token, league)

    print("Descargando clasificación y jornada en curso…")
    league_data = session.get(LEAGUE_DETAIL_URL, timeout=30).json().get("data") or {}
    rounds_data = session.get(ROUNDS_URL, timeout=30).json().get("data") or {}
    board = fetch_board(session, int(league["id"]))
    competition = fetch_competition_meta(session)
    season_rounds = competition.get("season_rounds") or []
    catalog_players = competition.get("players") or {}
    allowed_round_ids = season_round_ids(season_rounds) or None
    rounds_by_id = board_rounds(board, allowed_ids=allowed_round_ids)
    finished_nums = {r["number"] for r in rounds_by_id.values() if r["finished"]}
    print(f"Jornadas finalizadas: {sorted(finished_nums) or 'ninguna'}")
    postponed = pending_postponed_rounds(season_rounds)
    if postponed:
        print(
            "Pendientes de finalizar (aplazadas): "
            + ", ".join(p["name"] for p in postponed)
        )

    standings = league_data.get("standings") or []
    live_standings = (rounds_data.get("league") or {}).get("standings") or []
    live_by_id = {row.get("id"): row for row in live_standings}
    current_round_id = (rounds_data.get("round") or {}).get("id")
    current_round_id = int(current_round_id) if current_round_id is not None else None

    active = active_season_round(season_rounds)
    # Jornada en curso: preferir round activo del catálogo / live id
    if current_round_id and current_round_id in rounds_by_id:
        current_jornada = rounds_by_id[current_round_id]["number"]
        current_finished = rounds_by_id[current_round_id]["finished"]
    elif active and extract_jornada_number(active):
        current_jornada = extract_jornada_number(active)
        current_round_id = int(active["id"]) if active.get("id") is not None else None
        current_finished = False
    elif finished_nums:
        current_jornada = max(finished_nums) + 1
        current_finished = False
    else:
        current_jornada = 1
        current_finished = False

    # Si el live sigue anclado a una jornada ya cerrada, avanzar a la siguiente
    # activa/pendiente del calendario (p.ej. J4 final → J5 prematch).
    if current_finished:
        nxt = active
        if not nxt:
            for row in season_rounds:
                if row.get("part"):
                    continue
                if row.get("status") != "pending":
                    continue
                num = extract_jornada_number(row)
                if num is None:
                    continue
                if num > current_jornada or num not in finished_nums:
                    nxt = row
                    break
        if nxt and extract_jornada_number(nxt):
            current_jornada = extract_jornada_number(nxt)
            current_round_id = int(nxt["id"]) if nxt.get("id") is not None else None
            current_finished = False

    live_status = "final" if current_finished else "provisional"

    canonical_existing = {
        p["name"]: dict(p)
        for p in (current.get("players") or [])
        if p.get("name", "").strip().lower() != "bonilla"
    }
    accept_all_new = not canonical_existing

    by_name: dict[str, dict] = {}
    for name, prev in canonical_existing.items():
        by_name[name] = {
            "name": name,
            "biwenger_id": prev.get("biwenger_id"),
            "positions": {},
            "rounds": {},
            "points": 0,
            "team_value": 0,
            "team_value_inc": 0,
            "season_position": None,
            "icon": prev.get("icon"),
        }

    classification = []

    # 1) Resultados oficiales desde roundFinished
    for meta in rounds_by_id.values():
        if not meta["finished"] or not meta["results"]:
            continue
        jornada = meta["number"]
        for result in rank_results(meta["results"]):
            remote_name = result["name"]
            web_name = normalize_name(remote_name, aliases)
            if web_name.lower() == "bonilla":
                continue
            if not accept_all_new and web_name not in by_name:
                continue
            player = by_name.setdefault(
                web_name, {"name": web_name, "positions": {}, "rounds": {}}
            )
            set_round(
                player,
                jornada,
                result["position"],
                "final",
                result["points"],
                bonus=result["bonus"],
                bonus_reason=result["reason"],
                round_id=meta["round_id"],
            )

    # 2) Clasificación de temporada (standings).
    # No usar standings[].lastPositions para el ranking de jornada:
    # el índice no es fiable cuando hay jornadas fuera de orden (p.ej. J6
    # cerrada antes que J5) y sobrescribía el orden correcto del tablón
    # (roundFinished.results, ya ordenado por puntos).
    for row in standings:
        remote_name = (row.get("name") or "").strip()
        web_name = normalize_name(remote_name, aliases)
        if web_name.lower() == "bonilla":
            continue
        if not accept_all_new and web_name not in by_name:
            print(f"  (omitido sin alias) {remote_name}")
            continue

        player = by_name.setdefault(
            web_name, {"name": web_name, "positions": {}, "rounds": {}}
        )
        player["biwenger_id"] = row.get("id")
        player["icon"] = row.get("icon")
        player["points"] = int(row.get("points") or 0)
        player["team_value"] = int(row.get("teamValue") or 0)
        player["team_value_inc"] = int(row.get("teamValueInc") or 0)
        player["season_position"] = row.get("position")
        player["position_inc"] = row.get("positionInc")
        player["last_access"] = row.get("lastAccess")
        player["team_size"] = row.get("teamSize")
        live = live_by_id.get(row.get("id")) or {}
        lineup = live.get("lineup") if isinstance(live.get("lineup"), dict) else {}
        player["formation"] = lineup.get("type")
        player["lineup_counting"] = lineup.get("count")

        classification.append(
            {
                "name": web_name,
                "biwenger_name": remote_name,
                "position": row.get("position"),
                "points": player["points"],
                "team_value": player["team_value"],
                "team_value_inc": player["team_value_inc"],
                "position_inc": player.get("position_inc"),
                "icon": player.get("icon"),
                "team_size": player.get("team_size"),
                "last_access": player.get("last_access"),
                "formation": player.get("formation"),
                "lineup_counting": player.get("lineup_counting"),
            }
        )

    classification.sort(key=lambda x: (x["position"] is None, x["position"] or 999))

    # 3) Jornada en curso: puntos de once (fitness) > ranking live Biwenger.
    # /rounds/league a veces sigue mostrando puntos de la jornada anterior (espejo).
    if not current_finished and live_standings:
        prev_j = current_jornada - 1
        live_rows = []
        gw_rows = []
        for row in live_standings:
            remote_name = (row.get("name") or "").strip()
            web_name = normalize_name(remote_name, aliases)
            if web_name.lower() == "bonilla":
                continue
            if not accept_all_new and web_name not in by_name:
                continue
            pos = row.get("position")
            if pos is None:
                continue
            pts = int(row["points"]) if row.get("points") is not None else None
            live_rows.append((web_name, int(pos), pts))
            lineup = row.get("lineup") if isinstance(row.get("lineup"), dict) else {}
            gw = lineup_gameweek_points(
                lineup,
                catalog_players,
                jornada=current_jornada,
                current_jornada=current_jornada,
            )
            if gw is not None:
                gw_rows.append((web_name, gw))

        mirrored = is_mirrored_prematch(live_rows, by_name, prev_j, finished_nums)
        has_gw_scores = len(gw_rows) > 0 and any(pts != 0 for _, pts in gw_rows)
        gw_mirrored = is_mirrored_gameweek_points(
            gw_rows, by_name, prev_j, finished_nums
        )

        if has_gw_scores and not gw_mirrored:
            status = "provisional"
            live_status = "provisional"
            ranked = sorted(gw_rows, key=lambda x: (-x[1], x[0].lower()))
            print(
                f"Jornada {current_jornada}: provisional por puntos de once "
                f"({len(ranked)} managers)"
            )
            for pos, (web_name, pts) in enumerate(ranked, start=1):
                player = by_name.setdefault(
                    web_name, {"name": web_name, "positions": {}, "rounds": {}}
                )
                set_round(
                    player,
                    current_jornada,
                    pos,
                    status,
                    pts,
                    round_id=current_round_id,
                    points_source="lineup_fitness",
                )
        elif mirrored or gw_mirrored:
            live_status = "prematch"
            print(
                f"Jornada {current_jornada}: prematch (sin puntos nuevos aún; no suma al bote)"
            )
        else:
            live_status = "provisional"
            for web_name, pos, pts in live_rows:
                player = by_name.setdefault(
                    web_name, {"name": web_name, "positions": {}, "rounds": {}}
                )
                set_round(
                    player,
                    current_jornada,
                    pos,
                    "provisional",
                    pts,
                    round_id=current_round_id,
                )

    rounds_meta = {}
    all_j = set()
    for p in by_name.values():
        all_j.update(int(j) for j in p.get("positions", {}))
    all_j.add(current_jornada)
    rounds_by_number = {meta["number"]: meta for meta in rounds_by_id.values()}
    for j in sorted(all_j):
        sample_status = None
        for p in by_name.values():
            r = p.get("rounds", {}).get(str(j))
            if r:
                sample_status = r.get("status")
                break
        if j in finished_nums:
            status = "final"
        elif sample_status:
            status = sample_status
        elif j == current_jornada and not current_finished:
            status = live_status
        else:
            status = "provisional"
        rounds_meta[str(j)] = {
            "number": j,
            "status": status,
            "round_id": (rounds_by_number.get(j) or {}).get("round_id"),
            "started_at": (rounds_by_number.get(j) or {}).get("started_at"),
            "finished_at": (rounds_by_number.get(j) or {}).get("finished_at"),
        }

    players = sorted(by_name.values(), key=lambda p: (p.get("season_position") or 999))

    feed = enrich_league_feed(
        session,
        aliases=aliases,
        normalize_name=normalize_name,
        by_name=by_name,
        standings=standings,
        live_standings=live_standings,
        board=board,
        accept_all_new=accept_all_new,
        catalog=catalog_players,
        teams=competition.get("teams") or {},
        current_jornada=current_jornada,
    )

    # Partidos por jornada (el tablón solo traía el último bettingPool = jornada siguiente)
    season_starts = [
        int(m["started_at"])
        for m in rounds_by_id.values()
        if m.get("started_at") is not None
    ]
    min_board_date = (min(season_starts) - 14 * 86400) if season_starts else None
    fixtures_by_round = build_fixtures_by_round(
        board,
        rounds_meta,
        active_events=competition.get("active_events") or [],
        min_event_date=min_board_date,
    )
    fixtures = fixtures_by_round.get(str(current_jornada)) or feed.get("fixtures") or []

    # Reordenar tras enriquecer
    players = sorted(by_name.values(), key=lambda p: (p.get("season_position") or 999))

    payload = {
        **current,
        "league_name": league_data.get("name")
        or league.get("name")
        or current.get("league_name"),
        "season": current.get("season") or "2026-2027",
        "pot_rules": current.get("pot_rules") or DEFAULT_POT,
        "jornadas": current.get("jornadas") or 38,
        "last_place": len([p for p in players if not p.get("inactive")]) or 12,
        "active_managers": len([p for p in players if not p.get("inactive")]),
        "previous_season": current.get("previous_season"),
        "players": players,
        "classification": classification,
        "rounds_meta": rounds_meta,
        "current_jornada": current_jornada,
        "current_round_status": live_status,
        "current_round_id": current_round_id,
        "market": feed.get("market"),
        "activity": {
            "transfers": (feed.get("activity") or {}).get("transfers") or [],
            "market_deals": (feed.get("activity") or {}).get("market_deals") or [],
            "clause_increments": (feed.get("activity") or {}).get("clause_increments")
            or [],
        },
        "fixtures": fixtures,
        "fixtures_by_round": fixtures_by_round,
        "players_index": feed.get("players_index") or {},
        "postponed_rounds": postponed,
        "competition_rounds": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "short": r.get("short"),
                "status": r.get("status"),
                "part": r.get("part"),
            }
            for r in season_rounds
            if r.get("status") in ("finished", "active")
            or r.get("part")
            or (
                extract_jornada_number(r) is not None
                and extract_jornada_number(r) <= (current_jornada or 1) + 1
            )
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "biwenger-sync",
        "biwenger_league_id": league.get("id"),
    }

    print(
        f"Jornada actual: {current_jornada} ({live_status}) · managers: {len(players)}"
    )

    if dry_run:
        print("Dry-run: no se escribe liga.json")
        return payload

    save_json(DATA_PATH, payload)
    save_json(WEB_DATA_PATH, payload)
    print(f"Actualizado {DATA_PATH}")
    print(f"Actualizado {WEB_DATA_PATH} (GitHub Pages)")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Biwenger → data/liga.json")
    parser.add_argument("--dry-run", action="store_true", help="No escribe el JSON")
    args = parser.parse_args()
    try:
        sync(dry_run=args.dry_run)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
