# AGENTS — BOTE / Biwenger

Instrucciones para agentes que mantienen y evolucionan este repo.

## Qué es este proyecto

Web estática de consulta del **bote** y la **clasificación** de una liga privada de Biwenger.

- Temporada activa: `2026-2027` en `data/liga.json` (+ copia pública `web/data/liga.json`)
- Arrastre: bote acumulado `2025-2026` en `previous_season`
- Sync local con credenciales en `.env` (nunca commitear)
- Publicación: GitHub Pages desde la carpeta `web/` (workflow `.github/workflows/pages.yml`)

URL pública: `https://sergio-rdguez.github.io/Biwenger/`

## Agentes disponibles

| Agente | Cuándo usarlo | Archivo |
|--------|---------------|---------|
| Maintainer | Salud general, deudas técnicas, releases | [agents/maintainer.md](agents/maintainer.md) |
| Data Steward | Sync, jornadas, aliases, temporadas | [agents/data-steward.md](agents/data-steward.md) |
| Product UI | UI, pestañas, UX, diseño front | [agents/product-ui.md](agents/product-ui.md) |

## Skills (procedimientos)

| Skill | Uso |
|-------|-----|
| [sync-and-publish](skills/sync-and-publish/SKILL.md) | Sincronizar Biwenger y publicar en Pages |
| [biwenger-api](skills/biwenger-api/SKILL.md) | API no oficial, estados de jornada, aliases |
| [evolve-web](skills/evolve-web/SKILL.md) | Evolucionar la web (`web/`) |
| [pot-rules](skills/pot-rules/SKILL.md) | Reglas del bote y cálculos de adeuda |

Antes de una tarea, elige el agente + skill que correspondan y **lee su SKILL.md**.

## Reglas duras

1. **Nunca** commitear `.env`, tokens ni contraseñas.
2. Tras sync, actualizar **ambos**: `data/liga.json` y `web/data/liga.json`.
3. No romper GitHub Pages: el sitio público es estático; el botón «Importar» solo en localhost.
4. Respetar aliases en `data/aliases.json` (nombres cortos del Excel ↔ nombres Biwenger).
5. Bonilla está fuera de la liga activa; no reintroducirlo.
6. Responder al usuario en **español**.

## Mapa rápido de código

```
sync_biwenger.py     # login + board + rounds → JSON
serve.py             # local: estáticos + POST /api/sync
web/index.html|app.js|styles.css
web/data/liga.json   # publicado en Pages
data/liga.json       # fuente sync
data/aliases.json
data/temporada-2025-2026.json
.github/workflows/pages.yml
```

## Flujo de publicación (humano o agente)

```bash
python sync_biwenger.py
git add data/liga.json web/data/liga.json
git commit -m "Actualiza datos liga"
git push
```
