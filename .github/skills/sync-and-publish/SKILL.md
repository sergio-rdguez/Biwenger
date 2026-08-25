---
name: sync-and-publish
description: >-
  Sincroniza datos de la liga Biwenger a liga.json y publica en GitHub Pages.
  Use when the user asks to sync, importar, actualizar datos, publicar, push
  Pages, or refresh jornada/provisional standings.
---

# Sync and publish

## Cuándo

- Actualizar jornadas / provisionales
- Publicar para que lo vean los managers
- Tras cambiar aliases

## Pasos sync

1. Comprobar que existe `.env` con `BIWENGER_EMAIL` y `BIWENGER_PASSWORD` (no leer ni imprimir secretos).
2. Ejecutar:

```bash
python sync_biwenger.py
```

3. Verificar:
   - Se actualizan `data/liga.json` **y** `web/data/liga.json`
   - `current_jornada` / `current_round_status` coherentes (`final` | `provisional` | `prematch`)
   - No aparece Bonilla
   - No hay managers duplicados (si los hay → skill `biwenger-api` + `aliases.json`)

4. Probar local opcional: `python serve.py` → http://127.0.0.1:8765/web/

## Pasos publicar

Solo si el usuario pide publicar / push:

```bash
git add data/liga.json web/data/liga.json
git commit -m "Actualiza datos liga"
git push
```

Comprobar Action: `gh run list --workflow=pages.yml --limit 1`

URL: https://sergio-rdguez.github.io/Biwenger/

## Dry-run

```bash
python sync_biwenger.py --dry-run
```

## Errores frecuentes

| Síntoma | Acción |
|---------|--------|
| Login fallido | Revisar `.env` (sin echo de password) |
| Managers duplicados | Actualizar `data/aliases.json` y re-sync |
| Pages sin datos | Falta `web/data/liga.json` en el commit |
| Unicode Windows | El sync ya reconfigura stdout UTF-8 |

## No hacer

- Commitear `.env`
- Exponer `/api/sync` en Pages
- Editar a mano `web/data/liga.json` sin pasar por sync (salvo hotfix acordado)
