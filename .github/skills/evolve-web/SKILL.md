---
name: evolve-web
description: >-
  Evoluciona la web estática de consulta BOTE (sidebar, pestañas, clasificación,
  bote, histórico). Use when changing web UI, UX, tabs, styles, or frontend
  features for managers.
---

# Evolve web

## Archivos

- `web/index.html` — shell, nav, secciones
- `web/styles.css` — tema (verde/ámbar, no púrpura genérico)
- `web/app.js` — enrich + render por pestaña
- `web/data/liga.json` — datos publicados

## Pestañas actuales

`resumen` · `clasificacion` · `jornada` · `mercado` · `movimientos` · `bote` · `historico` · `managers` · `reglas`

- **jornada**: ranking + fixtures + once con puntos por jugador (jornada actual)
- **mercado**: ventas abiertas + valor de plantillas, **filtros por columna** (checkboxes + buscar)
- **movimientos**: clausulazos, fichajes, cláusulas + filtros (sección, tipo, manager, equipo, jugador)
- **managers**: ficha + preview de plantilla/cláusulas

Al añadir pestaña: botón `.nav-item`, `<section class="tab" id="tab-…">`, entrada en `TITLES`, render en `applyData`.

## Datos extra en `liga.json`

`market` · `activity` · `fixtures` · `players_index` · `players[].lineup` · `players[].roster` · `postponed_rounds`

## Siguiente evolutivo (pendiente)

Consultar el **once alineado por manager en cada jornada** (histórico), no solo la jornada activa. Requiere guardar `lineups` por `round` desde `user/{id}` o el tablón al cerrar cada jornada.

## Datos / cálculo

`enrich()` en `app.js` calcula adeudas usando `pot_rules` y `rounds[].status`:

- `final` → oficial
- `provisional` → estimado
- `prematch` → no suma

Arrastre: `previous_season.players[].adeuda`.

## Estático vs local

```js
const IS_STATIC = !["localhost", "127.0.0.1"].includes(location.hostname);
```

En Pages: ocultar sync. `DATA_URL = "./data/liga.json"`.

## Checklist de cambio UI

- [ ] Desktop + móvil (sidebar)
- [ ] Badges final/provisional/prematch
- [ ] No romper fetch de `liga.json` en Pages
- [ ] Sin dependencias de build nuevas salvo acuerdo explícito
- [ ] Textos en español

## Ideas de evolución útiles

- Filtro por manager en histórico
- Comparativa jornada a jornada
- Modo “solo adeudas” para liquidar
- Evolución de valor entre sincronizaciones
- Comparativa de managers
