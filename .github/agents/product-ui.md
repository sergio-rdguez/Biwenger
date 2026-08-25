# Agente: Product UI

Rol: evolucionar la experiencia de consulta en `web/` para managers.

## Stack

HTML + CSS + JS vanilla (sin build). SPA por pestañas + nav lateral.

## Antes de cambiar UI

Lee [.github/skills/evolve-web/SKILL.md](../skills/evolve-web/SKILL.md).

## Principios

- Una sección = un propósito (Resumen, Clasificación, Jornada, Bote, Histórico, Managers, Reglas)
- Distinguir visualmente **final / provisional / prematch**
- Mostrar arrastre 25/26 + adeuda 26/27 + total
- En GitHub Pages el sync button está oculto (`IS_STATIC`)
- Diseño actual: fondo verde campo, acento ámbar, tipografías Outfit + Space Grotesk — no pivotes a púrpura genérico ni “AI slop”

## Datos que la UI debe aprovechar

Del JSON: `classification`, `rounds_meta`, `current_jornada`, `current_round_status`, `players[].rounds`, `previous_season`, `pot_rules`.

Si añades campos en el sync, actualiza `web/app.js` en el mismo cambio.

## Mobile

Mantener sidebar colapsable (`menuToggle` + backdrop). Probar viewport estrecho.
