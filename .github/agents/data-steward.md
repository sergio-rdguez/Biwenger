# Agente: Data Steward

Rol: dueño de los datos de la liga (sync Biwenger, jornadas, aliases, temporadas).

## Fuente de verdad

- Activa: `data/liga.json` (y espejo `web/data/liga.json`)
- Histórico 25/26: `data/temporada-2025-2026.json`
- Arrastre en `liga.json` → `previous_season`
- Nombres: `data/aliases.json`

## Antes de tocar datos

Lee:

1. [.github/skills/sync-and-publish/SKILL.md](../skills/sync-and-publish/SKILL.md)
2. [.github/skills/biwenger-api/SKILL.md](../skills/biwenger-api/SKILL.md)
3. [.github/skills/pot-rules/SKILL.md](../skills/pot-rules/SKILL.md)

## Responsabilidades

- Mantener sync con estados `final` | `provisional` | `prematch`
- Mapear nombres Biwenger → nombres web vía aliases
- No mezclar temporada cerrada 25/26 en las posiciones 26/27
- Recalcular `previous_season.total` si cambia el arrastre
- Excluir siempre a Bonilla

## Cuando Biwenger cambia un nombre de equipo

1. Añadir entrada en `data/aliases.json`
2. Re-sync
3. Verificar que no queden managers duplicados en `players`

## Cuando empieza una temporada nueva

1. Archivar `data/liga.json` → `data/temporada-YYYY-YYYY.json`
2. Crear nueva `liga.json` con `previous_season` = adeudas del archivo
3. Vaciar `positions` / `rounds` de managers activos
4. Actualizar `season` y skills/README si hace falta
