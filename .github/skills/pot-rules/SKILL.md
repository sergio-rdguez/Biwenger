---
name: pot-rules
description: >-
  Reglas del bote de la liga: aportaciones por posición, arrastre 2025-2026,
  métricas Últ/Prim/Pag y cómo se calculan en Excel legado vs web. Use when
  changing pot fees, debts, season carryover, or bote calculations.
---

# Pot rules

## Aportación por jornada (activa)

| Puesto | € |
|--------|---|
| 8º | 0.5 |
| 9º | 1.0 |
| 10º | 1.5 |
| 11º | 2.0 |
| 12º | 2.5 |

Definido en `liga.json` → `pot_rules` y en sync `DEFAULT_POT`.

## Métricas (legado Excel)

- **Prim**: veces 1º
- **Pag**: jornadas con puesto > 7
- **Últ**: veces 13º + veces `last_place` (12) desde jornada 2
- **Adeuda oficial**: suma fees en jornadas `final`
- **Adeuda provisional**: fees en jornadas `provisional` (no `prematch`)
- **Total**: arrastre 25/26 + oficial (+ provisional en “estimado”)

## Arrastre 2025-2026

- Histórico completo: `data/temporada-2025-2026.json`
- Importes por manager: `liga.json` → `previous_season.players`
- Total actual (sin Bonilla): **286.5 €**

Bonilla **excluido** de la liga activa y del arrastre vivo.

## Al cambiar reglas

1. Actualizar `pot_rules` en `data/liga.json` (y tras sync, `web/data/`)
2. Ajustar UI de pestaña Reglas / KPIs si hace falta
3. Documentar aquí el cambio
4. No recalcular a mano el histórico 25/26 salvo petición explícita
