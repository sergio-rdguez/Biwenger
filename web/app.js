const DATA_URL = "./data/liga.json";
const IS_STATIC = !["localhost", "127.0.0.1"].includes(location.hostname);

const TITLES = {
  resumen: "Resumen",
  clasificacion: "Clasificación",
  jornada: "Jornada en vivo",
  mercado: "Plantillas y mercado",
  bote: "Bote y adeudas",
  historico: "Histórico",
  managers: "Managers",
  reglas: "Reglas",
};

const euro = (n) =>
  new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: Math.abs(n % 1) < 1e-9 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(Number(n) || 0);

const moneyM = (n) => {
  const v = Number(n) || 0;
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} M€`;
  return euro(v);
};

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatUpdated(iso) {
  if (!iso) return "sin sync";
  try {
    return new Intl.DateTimeFormat("es-ES", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function formatEpoch(seconds) {
  if (!seconds) return "—";
  try {
    return new Intl.DateTimeFormat("es-ES", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(Number(seconds) * 1000));
  } catch {
    return "—";
  }
}

function statusLabel(status) {
  if (status === "final") return "Final";
  if (status === "prematch") return "Pre-partido";
  return "Provisional";
}

function carryMap(data) {
  const map = new Map();
  for (const p of data.previous_season?.players || []) {
    map.set(p.name, Number(p.adeuda) || 0);
  }
  return map;
}

function roundStatus(data, jornada) {
  return data.rounds_meta?.[String(jornada)]?.status || "provisional";
}

function computeStats(player, potRules, lastPlace) {
  const rounds = player.rounds || {};
  const entries = Object.keys(player.positions || {})
    .map((j) => {
      const jornada = Number(j);
      const pos = Number(player.positions[j]);
      const meta = rounds[j] || {};
      return {
        jornada,
        pos,
        status: meta.status || "provisional",
        points: meta.points,
        bonus: meta.bonus,
        roundId: meta.round_id,
      };
    })
    .sort((a, b) => a.jornada - b.jornada);

  let ult = 0;
  let prim = 0;
  let pag = 0;
  let adeudaFinal = 0;
  let adeudaProv = 0;
  let bonusTotal = 0;

  for (const row of entries) {
    if (row.pos === 1) prim += 1;
    if (row.pos > 7) pag += 1;
    if (row.pos === 13) ult += 1;
    if (row.jornada >= 2 && row.pos === lastPlace) ult += 1;

    const fee = potRules[String(row.pos)];
    if (typeof fee === "number") {
      if (row.status === "final") adeudaFinal += fee;
      else if (row.status === "provisional") adeudaProv += fee;
      // prematch: se muestra ranking pero no suma al bote
    }
    if (row.status === "final") bonusTotal += Number(row.bonus) || 0;
  }

  const official = entries.filter((row) => row.status === "final");
  const averagePosition = official.length
    ? official.reduce((sum, row) => sum + row.pos, 0) / official.length
    : null;
  const bestPosition = official.length ? Math.min(...official.map((row) => row.pos)) : null;
  const worstPosition = official.length ? Math.max(...official.map((row) => row.pos)) : null;

  return {
    ult,
    prim,
    pag,
    adeudaFinal,
    adeudaProv,
    bonusTotal,
    averagePosition,
    bestPosition,
    worstPosition,
    entries,
  };
}

function enrich(data) {
  const potRules = data.pot_rules || {};
  const lastPlace = data.last_place || 12;
  const prev = carryMap(data);

  const players = (data.players || []).map((p) => {
    const stats = computeStats(p, potRules, lastPlace);
    const adeudaPrev = prev.get(p.name) || 0;
    return {
      ...p,
      ...stats,
      adeudaPrev,
      adeudaTotalOficial: adeudaPrev + stats.adeudaFinal,
      adeudaTotalConProv: adeudaPrev + stats.adeudaFinal + stats.adeudaProv,
      pointsPerMillion:
        Number(p.team_value) > 0 ? (Number(p.points) || 0) / (Number(p.team_value) / 1_000_000) : 0,
    };
  });

  const active = players.filter((p) => !p.inactive);
  const adeudadoOficial = active.reduce((s, p) => s + p.adeudaFinal, 0);
  const adeudadoProv = active.reduce((s, p) => s + p.adeudaProv, 0);
  const acumulado = Number(data.previous_season?.total) || 0;

  return {
    ...data,
    players: players.sort(
      (a, b) =>
        (a.season_position || 999) - (b.season_position || 999) ||
        a.name.localeCompare(b.name, "es")
    ),
    playersByDebt: [...players].sort(
      (a, b) => b.adeudaTotalConProv - a.adeudaTotalConProv || a.name.localeCompare(b.name, "es")
    ),
    playersByValue: [...players].sort(
      (a, b) => (Number(b.team_value) || 0) - (Number(a.team_value) || 0)
    ),
    totalTeamValue: players.reduce((sum, p) => sum + (Number(p.team_value) || 0), 0),
    totalDailyChange: players.reduce((sum, p) => sum + (Number(p.team_value_inc) || 0), 0),
    acumulado,
    adeudadoOficial,
    adeudadoProv,
    totalDeber: acumulado + adeudadoOficial,
    totalDeberProv: acumulado + adeudadoOficial + adeudadoProv,
  };
}

function setLivePill(data) {
  const pill = document.getElementById("livePill");
  const status = data.current_round_status || "provisional";
  const j = data.current_jornada || "—";
  if (status === "final") {
    pill.textContent = `J${j} cerrada`;
    pill.className = "pill final";
  } else if (status === "prematch") {
    pill.textContent = `J${j} pre-partido`;
    pill.className = "pill";
  } else {
    pill.textContent = `J${j} en vivo`;
    pill.className = "pill";
  }
}

function renderResumen(data) {
  document.getElementById("kpiGrid").innerHTML = `
    <div class="kpi"><span>Acumulado 25/26</span><strong>${euro(data.acumulado)}</strong></div>
    <div class="kpi"><span>26/27 oficial</span><strong>${euro(data.adeudadoOficial)}</strong></div>
    <div class="kpi"><span>Provisional jornada</span><strong>${euro(data.adeudadoProv)}</strong></div>
    <div class="kpi"><span>Total estimado</span><strong>${euro(data.totalDeberProv)}</strong></div>
  `;

  const top = (data.classification || data.players)
    .slice()
    .sort((a, b) => (a.position || a.season_position || 999) - (b.position || b.season_position || 999))
    .slice(0, 5);
  document.getElementById("resumenTop").innerHTML = `<ol class="mini-list">${top
    .map((p) => {
      const name = p.name;
      const pos = p.position || p.season_position;
      const pts = p.points ?? 0;
      return `<li><span>${pos}º ${escapeHtml(name)}</span><strong>${pts} pts</strong></li>`;
    })
    .join("")}</ol>`;

  const debt = data.playersByDebt.slice(0, 5);
  document.getElementById("resumenDeuda").innerHTML = `<ol class="mini-list">${debt
    .map(
      (p) =>
        `<li><span>${escapeHtml(p.name)}</span><strong class="money">${euro(
          p.adeudaTotalConProv
        )}</strong></li>`
    )
    .join("")}</ol>`;

  const j = data.current_jornada || 1;
  const status = roundStatus(data, j);
  const badge = document.getElementById("resumenJornadaBadge");
  badge.textContent = statusLabel(status);
  badge.className = `badge ${status}`;
  renderJornadaInto(data, j, "resumenJornada");

  const mostValuable = data.playersByValue[0];
  const bestEfficiency = [...data.players].sort(
    (a, b) => b.pointsPerMillion - a.pointsPerMillion
  )[0];
  const biggestRise = [...data.players].sort(
    (a, b) => (Number(b.team_value_inc) || 0) - (Number(a.team_value_inc) || 0)
  )[0];
  const mostBonus = [...data.players].sort((a, b) => b.bonusTotal - a.bonusTotal)[0];
  const insights = [
    ["Plantilla más valiosa", mostValuable?.name, moneyM(mostValuable?.team_value)],
    [
      "Mejor rendimiento",
      bestEfficiency?.name,
      `${bestEfficiency?.pointsPerMillion.toFixed(2) || "0.00"} pts/M€`,
    ],
    ["Mayor subida diaria", biggestRise?.name, moneyM(biggestRise?.team_value_inc)],
    ["Más premios", mostBonus?.name, moneyM(mostBonus?.bonusTotal)],
  ];
  document.getElementById("resumenInsights").innerHTML = insights
    .map(
      ([label, name, value]) => `<div class="insight">
        <span>${label}</span>
        <strong>${escapeHtml(name || "—")}</strong>
        <small>${value}</small>
      </div>`
    )
    .join("");
}

function renderClasificacion(data) {
  const rows = (data.classification || []).length
    ? data.classification
    : data.players.map((p) => ({
        name: p.name,
        position: p.season_position,
        points: p.points,
        team_value: p.team_value,
        team_value_inc: p.team_value_inc,
        position_inc: p.position_inc,
      }));

  document.getElementById("classBody").innerHTML = rows
    .map((r) => {
      const inc = r.position_inc;
      let incHtml = `<span class="muted">—</span>`;
      if (typeof inc === "number" && inc !== 0) {
        incHtml =
          inc > 0
            ? `<span class="pos-up">▲ ${inc}</span>`
            : `<span class="pos-down">▼ ${Math.abs(inc)}</span>`;
      }
      const day = r.team_value_inc || 0;
      const dayHtml =
        day > 0
          ? `<span class="pos-up">+${moneyM(day)}</span>`
          : day < 0
            ? `<span class="pos-down">${moneyM(day)}</span>`
            : `<span class="muted">0</span>`;
      return `<tr>
        <td>${r.position ?? "—"}</td>
        <td class="name-cell">${escapeHtml(r.name)}</td>
        <td>${r.points ?? 0}</td>
        <td>${moneyM(r.team_value)}</td>
        <td>${dayHtml}</td>
        <td>${incHtml}</td>
      </tr>`;
    })
    .join("");
}

function renderJornadaInto(data, jornada, targetId) {
  const list = document.getElementById(targetId);
  const potRules = data.pot_rules || {};
  const rows = data.players
    .map((p) => {
      const entry = p.entries.find((e) => e.jornada === jornada);
      if (!entry) return null;
      return {
        name: p.name,
        pos: entry.pos,
        points: entry.points,
        bonus: entry.bonus,
        status: entry.status,
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.pos - b.pos);

  if (!rows.length) {
    list.innerHTML =
      "<p class=\"hint\">Sin datos de esta jornada. Pulsa «Importar Biwenger».</p>";
    return;
  }

  list.innerHTML = `<ol class="rank-list">${rows
    .map((r) => {
      const fee = potRules[String(r.pos)];
      const pay = typeof fee === "number";
      const pts =
        r.points != null ? `${r.points} pts` : r.status === "provisional" ? "en vivo" : "—";
      const prize =
        r.status === "final" && r.bonus
          ? `Premio ${moneyM(r.bonus)}${pay ? ` · Bote ${euro(fee)}` : ""}`
          : pay
            ? `Bote ${euro(fee)}`
            : "—";
      return `<li class="${pay ? "pay" : ""}">
        <span class="pos">${r.pos}º</span>
        <span>${escapeHtml(r.name)}</span>
        <span class="muted">${pts}</span>
        <span>${prize}</span>
      </li>`;
    })
    .join("")}</ol>`;
}

function renderJornadaTab(data) {
  const select = document.getElementById("jornadaSelect");
  const jornadas = Object.keys(data.rounds_meta || {})
    .map(Number)
    .sort((a, b) => a - b);
  const fallback = [
    ...new Set(data.players.flatMap((p) => p.entries.map((e) => e.jornada))),
  ].sort((a, b) => a - b);
  const list = jornadas.length ? jornadas : fallback;

  select.innerHTML = list.map((j) => `<option value="${j}">Jornada ${j}</option>`).join("");
  if (!list.length) {
    document.getElementById("jornadaList").innerHTML =
      "<p class=\"hint\">Aún no hay jornadas. Importa desde Biwenger para ver el ranking provisional.</p>";
    document.getElementById("jornadaHint").textContent = "";
    return;
  }

  const current = data.current_jornada && list.includes(data.current_jornada)
    ? data.current_jornada
    : list[list.length - 1];
  select.value = String(current);

  const paint = () => {
    const j = Number(select.value);
    const status = roundStatus(data, j);
    const meta = data.rounds_meta?.[String(j)] || {};
    document.getElementById("jornadaHeading").textContent = `Jornada ${j}`;
    document.getElementById("jornadaHint").textContent =
      status === "final"
        ? `Resultado oficial cerrado en Biwenger${
            meta.finished_at ? ` · ${formatEpoch(meta.finished_at)}` : ""
          }.`
        : status === "prematch"
          ? `Jornada abierta${
              meta.started_at ? ` · ${formatEpoch(meta.started_at)}` : ""
            }, pero aún no hay puntos nuevos. No suma al bote.`
          : "Resultado provisional: puntos y posiciones se actualizan mientras se juega.";
    renderJornadaInto(data, j, "jornadaList");
  };
  select.onchange = paint;
  paint();
}

function renderMercado(data) {
  const averageValue = data.players.length ? data.totalTeamValue / data.players.length : 0;
  const highest = data.playersByValue[0];
  const bestEfficiency = [...data.players].sort(
    (a, b) => b.pointsPerMillion - a.pointsPerMillion
  )[0];
  document.getElementById("mercadoKpis").innerHTML = `
    <div class="kpi"><span>Valor total liga</span><strong>${moneyM(data.totalTeamValue)}</strong></div>
    <div class="kpi"><span>Media por plantilla</span><strong>${moneyM(averageValue)}</strong></div>
    <div class="kpi"><span>Variación diaria</span><strong class="${
      data.totalDailyChange >= 0 ? "pos-up" : "pos-down"
    }">${data.totalDailyChange > 0 ? "+" : ""}${moneyM(data.totalDailyChange)}</strong></div>
    <div class="kpi"><span>Mejor pts/M€</span><strong>${escapeHtml(
      bestEfficiency?.name || "—"
    )}</strong></div>
  `;

  document.getElementById("mercadoBody").innerHTML = data.playersByValue
    .map((p, index) => {
      const daily = Number(p.team_value_inc) || 0;
      return `<tr>
        <td>${index + 1}</td>
        <td class="name-cell">${escapeHtml(p.name)}${
          p.name === highest?.name ? ' <span class="tag">Top valor</span>' : ""
        }</td>
        <td>${moneyM(p.team_value)}</td>
        <td class="${daily >= 0 ? "pos-up" : "pos-down"}">${
          daily > 0 ? "+" : ""
        }${moneyM(daily)}</td>
        <td>${p.pointsPerMillion.toFixed(2)}</td>
        <td>${p.team_size ?? "—"}</td>
        <td>${escapeHtml(p.formation || "—")}</td>
        <td>${formatEpoch(p.last_access)}</td>
      </tr>`;
    })
    .join("");
}

function renderBote(data, query = "") {
  document.getElementById("boteKpis").innerHTML = `
    <div class="kpi"><span>Arrastre 25/26</span><strong>${euro(data.acumulado)}</strong></div>
    <div class="kpi"><span>Oficial 26/27</span><strong>${euro(data.adeudadoOficial)}</strong></div>
    <div class="kpi"><span>Con provisional</span><strong>${euro(data.totalDeberProv)}</strong></div>
  `;

  const q = query.trim().toLowerCase();
  document.getElementById("boteBody").innerHTML = data.playersByDebt
    .filter((p) => !q || p.name.toLowerCase().includes(q))
    .map(
      (p) => `<tr>
        <td class="name-cell">${escapeHtml(p.name)}</td>
        <td class="money">${euro(p.adeudaPrev)}</td>
        <td class="money">${euro(p.adeudaFinal)}</td>
        <td class="money">${euro(p.adeudaProv)}</td>
        <td class="money">${euro(p.adeudaTotalConProv)}</td>
        <td>${p.ult}</td>
        <td>${p.prim}</td>
        <td>${p.pag}</td>
      </tr>`
    )
    .join("");
}

function exportBoteCsv(data) {
  const headers = [
    "Manager",
    "Arrastre 25/26",
    "Oficial 26/27",
    "Provisional",
    "Total estimado",
    "Primeros",
    "Últimos",
    "Jornadas pagando",
  ];
  const rows = data.playersByDebt.map((p) => [
    p.name,
    p.adeudaPrev,
    p.adeudaFinal,
    p.adeudaProv,
    p.adeudaTotalConProv,
    p.prim,
    p.ult,
    p.pag,
  ]);
  const csv = [headers, ...rows]
    .map((row) =>
      row
        .map((value) => `"${String(value).replaceAll('"', '""')}"`)
        .join(";")
    )
    .join("\r\n");
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `bote-${data.season || "liga"}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderHistorico(data) {
  const jornadas = [
    ...new Set(data.players.flatMap((p) => p.entries.map((e) => e.jornada))),
  ].sort((a, b) => a - b);

  if (!jornadas.length) {
    document.getElementById("historicoWrap").innerHTML =
      "<p class=\"hint\">Sin jornadas todavía.</p>";
    return;
  }

  const head = jornadas.map((j) => `<th>J${j}</th>`).join("");
  const body = data.players
    .map((p) => {
      const cells = jornadas
        .map((j) => {
          const entry = p.entries.find((e) => e.jornada === j);
          if (!entry) return "<td class=\"muted\">—</td>";
          const fee = data.pot_rules?.[String(entry.pos)];
          const cls = [
            "heat",
            entry.pos === 1 ? "p1" : "",
            typeof fee === "number" ? "pay" : "",
            entry.status === "provisional" ? "prov" : "",
          ]
            .filter(Boolean)
            .join(" ");
          const title = entry.status === "provisional" ? "provisional" : "final";
          return `<td><span class="${cls}" title="${title}">${entry.pos}</span></td>`;
        })
        .join("");
      return `<tr><td class="name-cell">${escapeHtml(p.name)}</td>${cells}</tr>`;
    })
    .join("");

  document.getElementById("historicoWrap").innerHTML = `
    <table>
      <thead><tr><th>Manager</th>${head}</tr></thead>
      <tbody>${body}</tbody>
    </table>`;
}

function renderManagers(data, query = "") {
  const q = query.trim().toLowerCase();
  document.getElementById("managerGrid").innerHTML = data.players
    .filter((p) => !q || p.name.toLowerCase().includes(q))
    .map((p) => {
      const chips = p.entries
        .map((e) => {
          const fee = data.pot_rules?.[String(e.pos)];
          const cls = [
            "chip",
            e.pos === 1 ? "win" : "",
            typeof fee === "number" ? "pay" : "",
            e.status === "provisional" ? "provisional" : "",
          ]
            .filter(Boolean)
            .join(" ");
          return `<span class="${cls}">J${e.jornada} · ${e.pos}º${
            e.points != null ? ` · ${e.points}p` : ""
          }</span>`;
        })
        .join("");
      return `<article class="manager-card">
        <h3>${escapeHtml(p.name)}</h3>
        <dl>
          <dt>Puesto liga</dt><dd>${p.season_position ?? "—"}</dd>
          <dt>Puntos</dt><dd>${p.points ?? 0}</dd>
          <dt>Valor</dt><dd>${moneyM(p.team_value)}</dd>
          <dt>Adeuda total</dt><dd class="money">${euro(p.adeudaTotalConProv)}</dd>
          <dt>Prim / Últ</dt><dd>${p.prim} / ${p.ult}</dd>
          <dt>Posición media</dt><dd>${
            p.averagePosition == null ? "—" : p.averagePosition.toFixed(1)
          }</dd>
          <dt>Mejor / peor</dt><dd>${p.bestPosition ?? "—"}º / ${
            p.worstPosition ?? "—"
          }º</dd>
          <dt>Premios</dt><dd>${moneyM(p.bonusTotal)}</dd>
        </dl>
        <div class="chips">${chips || "<span class='muted'>Sin jornadas</span>"}</div>
      </article>`;
    })
    .join("");
}

function renderReglas(data) {
  const ul = document.getElementById("rulesList");
  ul.innerHTML = "";
  Object.entries(data.pot_rules || {})
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .forEach(([pos, fee]) => {
      const li = document.createElement("li");
      li.textContent = `${pos}º → ${euro(Number(fee))}`;
      ul.appendChild(li);
    });
  document.getElementById("rulesExtra").innerHTML = `
    <p>Arrastre temporada ${escapeHtml(data.previous_season?.season || "2025-2026")}: <strong class="money">${euro(
      data.acumulado
    )}</strong>.</p>
    <p>Las aportaciones provisionales se recalculan en cada importación hasta que Biwenger cierra la jornada.</p>`;
}

function applyData(raw) {
  window.__ligaRaw = raw;
  const data = enrich(raw);

  document.getElementById("seasonLabel").textContent = `Temporada ${data.season || ""}`;
  document.getElementById("sidebarSeason").textContent = data.season || "2026-2027";
  document.getElementById("leagueLabel").textContent = data.league_name || "Tu liga";
  document.getElementById("sidebarUpdated").textContent = `Act. ${formatUpdated(
    data.updated_at
  )}`;
  setLivePill(data);

  renderResumen(data);
  renderClasificacion(data);
  renderJornadaTab(data);
  renderMercado(data);
  renderBote(data, document.getElementById("searchBote").value);
  renderHistorico(data);
  renderManagers(data, document.getElementById("searchManagers").value);
  renderReglas(data);
  return data;
}

function setupNav() {
  const items = [...document.querySelectorAll(".nav-item")];
  const tabs = [...document.querySelectorAll(".tab")];
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.getElementById("sidebarBackdrop");

  const activate = (id) => {
    items.forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
    tabs.forEach((t) => t.classList.toggle("active", t.id === `tab-${id}`));
    document.getElementById("pageTitle").textContent = TITLES[id] || id;
    sidebar.classList.remove("open");
    backdrop.hidden = true;
  };

  items.forEach((btn) => btn.addEventListener("click", () => activate(btn.dataset.tab)));
  document.getElementById("menuToggle").addEventListener("click", () => {
    sidebar.classList.add("open");
    backdrop.hidden = false;
  });
  backdrop.addEventListener("click", () => {
    sidebar.classList.remove("open");
    backdrop.hidden = true;
  });
}

async function loadLiga() {
  const res = await fetch(DATA_URL, { cache: "no-store" });
  if (!res.ok) throw new Error(`No se pudo cargar ${DATA_URL}`);
  return res.json();
}

async function syncFromBiwenger() {
  const btn = document.getElementById("btnSync");
  const status = document.getElementById("syncStatus");
  btn.disabled = true;
  status.className = "sync-status";
  status.textContent = "Importando…";
  try {
    const res = await fetch("/api/sync", { method: "POST" });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok || !payload.ok) throw new Error(payload.error || `HTTP ${res.status}`);
    applyData(payload.data || (await loadLiga()));
    status.className = "sync-status ok";
    status.textContent = `OK · J${payload.data?.current_jornada || "?"} ${
      payload.data?.current_round_status || ""
    }`;
  } catch (err) {
    status.className = "sync-status err";
    status.textContent = err.message || "Error al importar";
  } finally {
    btn.disabled = false;
  }
}

async function boot() {
  setupNav();
  applyData(await loadLiga());

  const btn = document.getElementById("btnSync");
  const status = document.getElementById("syncStatus");
  if (IS_STATIC) {
    btn.hidden = true;
    status.className = "sync-status";
    status.textContent = "Datos publicados desde local";
  } else {
    btn.addEventListener("click", syncFromBiwenger);
  }

  document.getElementById("searchBote").addEventListener("input", (e) => {
    renderBote(enrich(window.__ligaRaw), e.target.value);
  });
  document.getElementById("searchManagers").addEventListener("input", (e) => {
    renderManagers(enrich(window.__ligaRaw), e.target.value);
  });
  document.getElementById("exportBote").addEventListener("click", () => {
    exportBoteCsv(enrich(window.__ligaRaw));
  });
}

boot().catch((err) => {
  document.querySelector("main").innerHTML = `<section class="panel"><p>Error: ${escapeHtml(
    err.message
  )}. Arranca con <code>python serve.py</code>.</p></section>`;
});
