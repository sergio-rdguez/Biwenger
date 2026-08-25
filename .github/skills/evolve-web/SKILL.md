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

`resumen` · `clasificacion` · `jornada` · `mercado` · `bote` · `historico` · `managers` · `reglas`

Al añadir pestaña: botón `.nav-item`, `<section class="tab" id="tab-…">`, entrada en `TITLES`, render en `applyData`.

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
