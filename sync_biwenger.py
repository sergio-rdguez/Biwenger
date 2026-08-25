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


def board_rounds(board: list[dict]) -> dict[int, dict]:
    """round_id -> {number, finished, results}."""
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
        entry = by_id.setdefault(
            rid, {"number": num, "finished": False, "results": None}
        )
        entry["number"] = num
        if event.get("type") == "roundFinished":
            entry["finished"] = True
            results = content.get("results")
            entry["results"] = results if isinstance(results, list) else []
    return by_id


def rank_results(results: list[dict]) -> list[tuple[str, int, int]]:
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
            }
        )
    if any(s["explicit"] is not None for s in scored):
        scored.sort(
            key=lambda s: (s["explicit"] is None, s["explicit"] or 999, -s["points"], s["idx"])
        )
    else:
        scored.sort(key=lambda s: (-s["points"], s["idx"]))
    return [(s["name"], i, s["points"]) for i, s in enumerate(scored, start=1)]


def set_round(
    player: dict,
    jornada: int,
    position: int,
    status: str,
    points: int | None = None,
) -> None:
    player["positions"][str(jornada)] = int(position)
    player["rounds"][str(jornada)] = {
        "position": int(position),
        "status": status,
        "points": points,
    }


def sync(dry_run: bool = False) -> dict:
    email = os.getenv("BIWENGER_EMAIL") or os.getenv("BIWENGER_USERNAME")
    password = os.getenv("BIWENGER_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Faltan BIWENGER_EMAIL y BIWENGER_PASSWORD. Copia .env.example a .env"
        )

    aliases = load_aliases()
    current = load_json(
        DATA_PATH,
        {
            "league_name": "Liga Biwenger",
            "season": "2026-2027",
            "pot_rules": DEFAULT_POT,
            "jornadas": 38,
            "players": [],
        },
    )

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
    rounds_by_id = board_rounds(board)
    finished_nums = {r["number"] for r in rounds_by_id.values() if r["finished"]}
    print(f"Jornadas finalizadas: {sorted(finished_nums) or 'ninguna'}")

    standings = league_data.get("standings") or []
    live_standings = (rounds_data.get("league") or {}).get("standings") or []
    current_round_id = (rounds_data.get("round") or {}).get("id")
    current_round_id = int(current_round_id) if current_round_id is not None else None

    # Jornada en curso según round id (p.ej. 4900 = Jornada 2)
    if current_round_id and current_round_id in rounds_by_id:
        current_jornada = rounds_by_id[current_round_id]["number"]
        current_finished = rounds_by_id[current_round_id]["finished"]
    elif finished_nums:
        current_jornada = max(finished_nums) + 1
        current_finished = False
    else:
        current_jornada = 1
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
        for remote_name, place, pts in rank_results(meta["results"]):
            web_name = normalize_name(remote_name, aliases)
            if web_name.lower() == "bonilla":
                continue
            if not accept_all_new and web_name not in by_name:
                continue
            player = by_name.setdefault(
                web_name, {"name": web_name, "positions": {}, "rounds": {}}
            )
            set_round(player, jornada, place, "final", pts)

    # 2) Clasificación de temporada + lastPositions (rellena huecos)
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

        for idx, pos in enumerate(row.get("lastPositions") or []):
            jornada = idx + 1
            # No pisar un final ya cargado desde el tablón
            existing = player["rounds"].get(str(jornada))
            if existing and existing.get("status") == "final":
                continue
            status = "final" if jornada in finished_nums else "provisional"
            set_round(player, jornada, int(pos), status, existing.get("points") if existing else None)

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
            }
        )

    classification.sort(key=lambda x: (x["position"] is None, x["position"] or 999))

    # 3) Jornada en curso (provisional): ranking live de /rounds/league
    if not current_finished and live_standings:
        # Si todos los puntos coinciden con la jornada final anterior,
        # Biwenger aún no ha empezado a puntuar: marcar prematch (sin bote).
        prev_j = current_jornada - 1
        mirrored = True
        live_rows = []
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
            prev = by_name.get(web_name, {}).get("rounds", {}).get(str(prev_j))
            if not prev or prev.get("status") != "final" or prev.get("points") != pts:
                mirrored = False

        status = "prematch" if (mirrored and prev_j in finished_nums and live_rows) else "provisional"
        if status == "prematch":
            live_status = "prematch"
            print(
                f"Jornada {current_jornada}: prematch (sin puntos nuevos aún; no suma al bote)"
            )

        for web_name, pos, pts in live_rows:
            player = by_name.setdefault(
                web_name, {"name": web_name, "positions": {}, "rounds": {}}
            )
            set_round(player, current_jornada, pos, status, pts)

    rounds_meta = {}
    all_j = set()
    for p in by_name.values():
        all_j.update(int(j) for j in p.get("positions", {}))
    all_j.add(current_jornada)
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
            "round_id": current_round_id if j == current_jornada else None,
        }

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
