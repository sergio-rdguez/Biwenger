# BOTE — consulta de liga Biwenger

Web gratuita para que los managers consulten **posiciones por jornada**, **adeudas** y **bote**, en lugar del Excel.

## Arranque rápido (local)

```bash
pip install -r requirements.txt
python serve.py
```

Abre http://127.0.0.1:8080/web/

- `data/liga.json` → temporada activa **2026-2027** (+ arrastre del bote 25/26)
- `data/temporada-2025-2026.json` → histórico completo del Excel (bote acumulado)

## Sincronizar con tu liga de Biwenger

Desde la web: botón **Importar desde Biwenger** (usa el `.env` en el servidor; no expone la contraseña al navegador).

También por terminal:

```bash
python sync_biwenger.py
```

1. Copia `.env.example` → `.env` y rellena email/contraseña.
2. Si el nombre del equipo en Biwenger no coincide con el de la web, edita `data/aliases.json`.
3. Arranca `python serve.py` y pulsa el botón, o ejecuta el script.
## Temporadas

| Archivo | Contenido |
|---------|-----------|
| `data/liga.json` | Temporada activa **2026-2027** + arrastre del bote 25/26 |
| `data/temporada-2025-2026.json` | Histórico completo (Excel) |

La web muestra por manager: deuda **25/26** + deuda **26/27** + **total**.

## Qué calcula la web

Misma lógica que el Excel **Bote** para la temporada activa:

| Concepto | Regla |
|----------|--------|
| Adeuda 26/27 | Suma por quedar 8º–12º (0,5 / 1 / 1,5 / 2 / 2,5 €) |
| Acumulado 25/26 | Bote cerrado del Excel (291 €) |
| Total a deber | Acumulado + adeuda nueva |

## Publicar en GitHub Pages (gratis)

Flujo pensado: **sincronizas en local** y **publicas** para que cualquiera consulte.

```bash
python sync_biwenger.py          # actualiza data/ y web/data/
git add data/liga.json web/data/liga.json
git commit -m "Actualiza datos liga"
git push
```

En 1–2 minutos la web pública se actualiza sola (Action `Deploy GitHub Pages`).

El botón «Importar Biwenger» solo aparece en local (`python serve.py`). En Pages no se exponen credenciales.

## Archivos

| Ruta | Uso |
|------|-----|
| `web/` | Interfaz de consulta (se publica en Pages) |
| `web/data/liga.json` | Copia pública de los datos |
| `data/liga.json` | Datos del bote (sync local) |
| `data/aliases.json` | Alias nombre Biwenger → nombre web |
| `sync_biwenger.py` | Sync API Biwenger |
| `serve.py` | Servidor local |
| `Biwenger_2026.xlsx` | Origen histórico (opcional) |

## Privacidad

- La web solo muestra lo que hay en `liga.json` (nombres de managers y posiciones).
- El login de Biwenger solo ocurre en tu máquina al lanzar el sync.
