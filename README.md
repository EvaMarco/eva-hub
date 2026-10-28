# Hub de Eva

Una página con el estado de mi trabajo en Penpot: lo que me toca hacer, mis PRs abiertas, la épica de migración al Design System y mis tareas e ideas.

## Qué muestra

- **Ahora:** las PRs que se pueden mergear, tienen el CI roto, tienen cambios pedidos o cuya nota dice que me tocan; mis tareas por hacer; lo que espera a otros; lo mergeado en los últimos 14 días; las issues asignadas.
- **PRs:** todas mis PRs abiertas en penpot/penpot con su estado, CI y siguiente paso. Filtra por estado o busca.
- **Épica DS:** el progreso de #12375 y del grupo en curso (#12376), con el estado real de cada PR y las filas de la tabla del grupo que se han quedado desactualizadas. Cada grupo muestra también sus zonas (carpetas o archivos que aún usan el control antiguo) y cuántas issues harían falta, aproximadamente.
- **Tareas e ideas:** las issues de este repo (ideas rápidas) y `data/tasks.yml`.

## De dónde salen los datos

| Archivo | Quién lo escribe |
|---|---|
| `data/notes.yml` | El siguiente paso de cada PR. Lo edito yo o Claude Code. |
| `data/tasks.yml` | Tareas que no son una PR o que abarcan varias. |
| Issues de este repo | Ideas rápidas: se crean desde GitHub (también desde el móvil). |
| `data/zones.yml` | `scripts/zones.py <penpot>/frontend`, a mano: inventario de zonas de cada grupo de la épica y estimación de issues. |
| `data/cache/github.json` | `scripts/sync.py`, con `gh`. No se sube al repo. |

`render.py` lo junta todo en `site/index.html`, que tampoco se sube.

## Cuándo se actualiza

La Action `.github/workflows/hub.yml` sincroniza y publica en GitHub Pages:

- cada 30 minutos, de lunes a viernes en horario de trabajo;
- con cada push a `main` (por ejemplo, al cambiar notas o tareas);
- al crear, editar o cerrar una issue (idea);
- a mano, con el enlace "Actualizar ahora" de la página (Actions → Hub → Run workflow).

## Probarlo en local

```
scripts/serve.sh             # sincroniza, genera y sirve en http://localhost:8800
scripts/serve.sh --no-sync   # solo regenera, con los últimos datos
```

Necesita `gh` con sesión iniciada y PyYAML. Recarga la página tras volver a lanzarlo.

## Puesta en marcha (una vez)

1. Crear el repo `EvaMarco/eva-hub` en GitHub y subir esto.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → Hub → Run workflow. La página queda en https://evamarco.github.io/eva-hub/.

El repo es público, así que las notas, las tareas y las ideas también lo son. No pongas nada privado.
