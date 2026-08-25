const DATA_URL = "./data/liga.json";
const IS_STATIC = !["localhost", "127.0.0.1"].includes(location.hostname);

const TITLES = {
  resumen: "Resumen",
  clasificacion: "Clasificación",
  jornada: "Jornada en vivo",
  mercado: "Mercado",
  movimientos: "Movimientos",
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

function renderJornadaInto(data, jornada, targetId, { expandable = false } = {}) {
  const list = document.getElementById(targetId);
  const potRules = data.pot_rules || {};
  const showXi = expandable && jornada === data.current_jornada;
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
        lineup: p.lineup,
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
      const xiSum =
        showXi && r.lineup?.points_sum != null
          ? ` · XI ${r.lineup.points_sum} pts`
          : "";
      const detail = showXi ? renderLineupDetail(r.lineup) : "";
      return `<li class="rank-item ${pay ? "pay" : ""} ${showXi ? "expandable" : ""}">
        <div class="rank-row">
          <span class="pos">${r.pos}º</span>
          <span class="rank-name">${escapeHtml(r.name)}</span>
          <span class="muted">${pts}${xiSum}</span>
          <span>${prize}</span>
        </div>
        ${detail}
      </li>`;
    })
    .join("")}</ol>`;
}

function renderLineupDetail(lineup) {
  if (!lineup?.starters?.length) {
    return `<div class="lineup-detail"><p class="hint">Sin once disponible.</p></div>`;
  }
  const starters = lineup.starters
    .map(
      (p) => `<tr>
        <td><span class="pos-tag">${escapeHtml(p.position_label || "?")}</span></td>
        <td>${escapeHtml(p.name)}</td>
        <td class="muted">${escapeHtml(p.team || "—")}</td>
        <td class="pts-cell">${p.points_jornada ?? p.points_last ?? "—"}</td>
      </tr>`
    )
    .join("");
  const bench = (lineup.bench || [])
    .map(
      (p) => `<tr class="bench-row">
        <td><span class="pos-tag muted">${escapeHtml(p.position_label || "?")}</span></td>
        <td>${escapeHtml(p.name)}</td>
        <td class="muted">${escapeHtml(p.team || "—")}</td>
        <td class="pts-cell muted">${p.points_jornada ?? p.points_last ?? "—"}</td>
      </tr>`
    )
    .join("");
  return `<div class="lineup-detail">
    <div class="lineup-meta">
      <span>${escapeHtml(lineup.formation || "—")}</span>
      <strong>Suma titulares: ${lineup.points_sum ?? 0} pts</strong>
    </div>
    <div class="table-wrap compact">
      <table class="lineup-table">
        <thead><tr><th>Pos</th><th>Jugador</th><th>Equipo</th><th>Pts</th></tr></thead>
        <tbody>${starters}${bench}</tbody>
      </table>
    </div>
  </div>`;
}

function renderFixtures(data, targetId) {
  const el = document.getElementById(targetId);
  if (!el) return;
  const fixtures = data.fixtures || [];
  if (!fixtures.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = fixtures
    .map((g) => {
      const score =
        g.home_score != null && g.away_score != null
          ? `${g.home_score} – ${g.away_score}`
          : "vs";
      const diff =
        g.home_difficulty != null || g.away_difficulty != null
          ? `<small>Dif. ${g.home_difficulty ?? "—"} / ${g.away_difficulty ?? "—"}</small>`
          : "";
      return `<div class="fixture-card">
        <span class="fixture-home">${escapeHtml(g.home || "?")}</span>
        <span class="fixture-score">${score}</span>
        <span class="fixture-away">${escapeHtml(g.away || "?")}</span>
        <span class="fixture-meta">${formatEpoch(g.date)} · ${escapeHtml(
          g.status || ""
        )}${diff}</span>
      </div>`;
    })
    .join("");
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
    document.getElementById("jornadaFixtures").innerHTML = "";
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
    const xiNote =
      j === data.current_jornada
        ? " Debajo de cada manager: once y puntos por jugador (última puntuación Biwenger)."
        : "";
    document.getElementById("jornadaHint").textContent =
      (status === "final"
        ? `Resultado oficial cerrado en Biwenger${
            meta.finished_at ? ` · ${formatEpoch(meta.finished_at)}` : ""
          }.`
        : status === "prematch"
          ? `Jornada abierta${
              meta.started_at ? ` · ${formatEpoch(meta.started_at)}` : ""
            }, pero aún no hay puntos nuevos. No suma al bote.`
          : "Resultado provisional: puntos y posiciones se actualizan mientras se juega.") +
      xiNote;
    renderFixtures(data, "jornadaFixtures");
    renderJornadaInto(data, j, "jornadaList", { expandable: true });
  };
  select.onchange = paint;
  paint();
}

function renderMercado(data, query = "") {
  const averageValue = data.players.length ? data.totalTeamValue / data.players.length : 0;
  const highest = data.playersByValue[0];
  const bestEfficiency = [...data.players].sort(
    (a, b) => b.pointsPerMillion - a.pointsPerMillion
  )[0];
  const sales = data.market?.sales || [];
  const openSales = sales.length;
  document.getElementById("mercadoKpis").innerHTML = `
    <div class="kpi"><span>Ventas abiertas</span><strong>${openSales}</strong></div>
    <div class="kpi"><span>Valor total liga</span><strong>${moneyM(data.totalTeamValue)}</strong></div>
    <div class="kpi"><span>Media por plantilla</span><strong>${moneyM(averageValue)}</strong></div>
    <div class="kpi"><span>Variación diaria</span><strong class="${
      data.totalDailyChange >= 0 ? "pos-up" : "pos-down"
    }">${data.totalDailyChange > 0 ? "+" : ""}${moneyM(data.totalDailyChange)}</strong></div>
  `;

  const q = query.trim().toLowerCase();
  const filtered = sales.filter((s) => {
    if (!q) return true;
    const hay = `${s.player || ""} ${s.seller || ""} ${s.team || ""}`.toLowerCase();
    return hay.includes(q);
  });
  const salesBody = document.getElementById("salesBody");
  if (!filtered.length) {
    salesBody.innerHTML = `<tr><td colspan="7" class="muted">${
      sales.length ? "Sin coincidencias." : "Sin ventas abiertas (o aún no sincronizado)."
    }</td></tr>`;
  } else {
    salesBody.innerHTML = filtered
      .slice()
      .sort((a, b) => (a.until || 0) - (b.until || 0))
      .map(
        (s) => `<tr>
          <td class="name-cell">${escapeHtml(s.player || `#${s.player_id}`)}</td>
          <td>${escapeHtml(s.position_label || "—")}</td>
          <td>${escapeHtml(s.team || "—")}</td>
          <td>${moneyM(s.price)}</td>
          <td>${s.points_last ?? "—"}</td>
          <td>${escapeHtml(s.seller || "Agencia")}</td>
          <td>${formatEpoch(s.until)}</td>
        </tr>`
      )
      .join("");
  }

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

function feedItem(html) {
  return `<div class="feed-item">${html}</div>`;
}

function renderMovimientos(data) {
  const act = data.activity || {};
  const transfers = act.transfers || [];
  const clauses = act.clause_increments || [];
  const deals = act.market_deals || [];

  document.getElementById("movTransfers").innerHTML = transfers.length
    ? transfers
        .map((t) => {
          const who = t.to
            ? `${escapeHtml(t.from || "?")} → ${escapeHtml(t.to)}`
            : `Sale de ${escapeHtml(t.from || "?")}`;
          return feedItem(`
            <div class="feed-top">
              <strong>${escapeHtml(t.player || `#${t.player_id}`)}</strong>
              <span class="tag">${escapeHtml(t.kind || "transfer")}</span>
            </div>
            <div class="feed-meta">${who} · ${moneyM(t.amount)}</div>
            <div class="feed-sub">${escapeHtml(t.team || "")} · ${formatEpoch(t.date)}</div>
          `);
        })
        .join("")
    : `<p class="hint">Sin clausulazos recientes.</p>`;

  document.getElementById("movClauses").innerHTML = clauses.length
    ? clauses
        .map((c) =>
          feedItem(`
            <div class="feed-top">
              <strong>${escapeHtml(c.player || `#${c.player_id}`)}</strong>
              <span class="muted">${escapeHtml(c.manager || "—")}</span>
            </div>
            <div class="feed-meta">+${moneyM(c.amount)}${
              c.release_clause != null ? ` · cláusula ${moneyM(c.release_clause)}` : ""
            }</div>
            <div class="feed-sub">${formatEpoch(c.date)}</div>
          `)
        )
        .join("")
    : `<p class="hint">Sin subidas recientes.</p>`;

  document.getElementById("movMarket").innerHTML = deals.length
    ? deals
        .map((d) => {
          const bids = (d.bids || [])
            .slice(0, 3)
            .map((b) => `${escapeHtml(b.manager || "?")} ${moneyM(b.amount)}`)
            .join(" · ");
          return feedItem(`
            <div class="feed-top">
              <strong>${escapeHtml(d.player || `#${d.player_id}`)}</strong>
              <span class="muted">→ ${escapeHtml(d.to || "—")}</span>
            </div>
            <div class="feed-meta">${moneyM(d.amount)}${
              d.from ? ` · de ${escapeHtml(d.from)}` : ""
            }</div>
            <div class="feed-sub">${formatEpoch(d.date)}${bids ? ` · ${bids}` : ""}</div>
          `);
        })
        .join("")
    : `<p class="hint">Sin fichajes de mercado recientes.</p>`;
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
      const rosterTop = (p.roster || [])
        .slice(0, 8)
        .map((pl) => {
          const mark = pl.in_xi ? "★" : pl.on_bench ? "·" : "";
          return `<li>
            <span>${mark} ${escapeHtml(pl.position_label || "?")} ${escapeHtml(pl.name)}</span>
            <span class="muted">${pl.clause != null ? moneyM(pl.clause) : moneyM(pl.price)}</span>
          </li>`;
        })
        .join("");
      const xiPts = p.lineup?.points_sum;
      return `<article class="manager-card">
        <h3>${escapeHtml(p.name)}</h3>
        <dl>
          <dt>Puesto liga</dt><dd>${p.season_position ?? "—"}</dd>
          <dt>Puntos</dt><dd>${p.points ?? 0}</dd>
          <dt>Valor</dt><dd>${moneyM(p.team_value)}</dd>
          <dt>Saldo / max puja</dt><dd>${
            p.balance != null ? moneyM(p.balance) : "—"
          } / ${p.max_bid != null ? moneyM(p.max_bid) : "—"}</dd>
          <dt>Once jornada</dt><dd>${
            xiPts != null ? `${xiPts} pts · ${escapeHtml(p.lineup?.formation || "")}` : "—"
          }</dd>
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
        ${
          rosterTop
            ? `<div class="roster-preview"><h4>Plantilla</h4><ul>${rosterTop}</ul>${
                (p.roster || []).length > 8
                  ? `<p class="hint">+${(p.roster || []).length - 8} más</p>`
                  : ""
              }</div>`
            : ""
        }
      </article>`;
    })
    .join("");
}

const CLAUSE_TIERS = [
  ["Hasta 200.000 €", "400 %"],
  ["Hasta 300.000 €", "350 %"],
  ["Hasta 400.000 €", "300 %"],
  ["Hasta 500.000 €", "280 %"],
  ["Hasta 600.000 €", "260 %"],
  ["Hasta 700.000 €", "240 %"],
  ["Hasta 800.000 €", "220 %"],
  ["Hasta 900.000 €", "210 %"],
  ["Hasta 1.000.000 €", "200 %"],
  ["Hasta 1.250.000 €", "180 %"],
  ["Hasta 1.500.000 €", "170 %"],
  ["Hasta 3.500.000 €", "150 %"],
  ["Hasta 6.500.000 €", "130 %"],
  ["Hasta 12.000.000 €", "120 %"],
  ["Hasta 25.000.000 €", "110 %"],
  ["Más de 25.000.000 €", "105 %"],
];

function renderReglas(data) {
  const potRows = Object.entries(data.pot_rules || {})
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(
      ([pos, fee]) =>
        `<tr><td>${pos}º</td><td class="money">${euro(Number(fee))}</td></tr>`
    )
    .join("");

  const clauseRows = CLAUSE_TIERS.map(
    ([range, pct]) => `<tr><td>${range}</td><td>${pct}</td></tr>`
  ).join("");

  document.getElementById("rulesContent").innerHTML = `
    <article class="panel rules">
      <h2>Espíritu de la liga</h2>
      <p>Es un juego <strong>individual</strong>. Cada manager compite por sí mismo: no se permiten pactos, estrategias de equipo ni cualquier movimiento acordado fuera del mercado limpio.</p>
      <ul class="rules-bullets">
        <li>Prohibidos los clausulazos, fichajes o maniobras coordinadas tras hablarlo con otro participante.</li>
        <li>No se puede subir el valor de la cláusula de un jugador mediante intercambios: en un trueque, la cláusula debe mantenerse igual o bajar.</li>
        <li>El incumplimiento se considera antideportivo y queda a criterio de la organización de la liga.</li>
      </ul>
    </article>

    <article class="panel rules">
      <h2>Economía inicial y primas</h2>
      <p>Al empezar la temporada, el saldo inicial es <strong>40 M€ menos el valor de mercado de un equipo aleatorio</strong> de LaLiga. Así todos parten con una base distinta y aleatoria.</p>
      <ul class="rules-bullets">
        <li><strong>Prima por puntos:</strong> 50.000 € por cada punto que aporte un jugador.</li>
        <li>El resto de primas y bonificaciones se consultan en los ajustes de Biwenger de la liga.</li>
        <li>Se pueden <strong>hacer hasta 3 clausulazos y recibir hasta 3 clausulazos por día</strong>.</li>
      </ul>
    </article>

    <article class="panel rules">
      <h2>Cláusulas base</h2>
      <p>La cláusula mínima de un jugador se calcula aplicando un porcentaje sobre su valor de mercado, según estos tramos:</p>
      <div class="table-wrap">
        <table class="rules-table">
          <thead><tr><th>Valor de mercado</th><th>Cláusula base</th></tr></thead>
          <tbody>${clauseRows}</tbody>
        </table>
      </div>
      <div class="rules-callout">
        <strong>Dinero a meter en cláusulas</strong>
        <p>Puedes destinar a cláusulas hasta el <strong>200 % del saldo invertido</strong> (el capital ya empleado en plantilla). Ese dinero queda bloqueado en la cláusula: <strong>no se puede recuperar lo invertido</strong> en ellas.</p>
      </div>
    </article>

    <article class="panel rules">
      <h2>Cesiones</h2>
      <ul class="rules-bullets">
        <li><strong>No se pueden ceder porteros.</strong></li>
        <li>Precio mínimo de la cesión: <strong>max(500.000 €; 10 % del valor de mercado)</strong>.</li>
        <li>Como máximo, <strong>dar o recibir 1 jugador por jornada</strong>.</li>
        <li>En las <strong>últimas 8 jornadas</strong> de la temporada <strong>no hay cesiones</strong>.</li>
      </ul>
    </article>

    <article class="panel rules">
      <h2>Bote de final de temporada</h2>
      <p>Cada jornada, quienes terminan del 8.º al 12.º aportan al bote común destinado a la <strong>cena de final de temporada</strong>. Las aportaciones provisionales se muestran en vivo y solo se consolidan cuando Biwenger cierra la jornada.</p>
      <div class="table-wrap">
        <table class="rules-table rules-table-compact">
          <thead><tr><th>Posición</th><th>Aportación</th></tr></thead>
          <tbody>${potRows}</tbody>
        </table>
      </div>
      <p class="rules-note">Arrastre temporada ${escapeHtml(
        data.previous_season?.season || "2025-2026"
      )}: <strong class="money">${euro(data.acumulado)}</strong> (sin Bonilla).</p>
    </article>
  `;
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
  renderMercado(data, document.getElementById("searchMarket")?.value || "");
  renderMovimientos(data);
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
  document.getElementById("searchMarket")?.addEventListener("input", (e) => {
    renderMercado(enrich(window.__ligaRaw), e.target.value);
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
