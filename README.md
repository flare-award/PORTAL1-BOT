# Portal 1 Bot - 3D World Model Approach

**AI-агент, который воспринимает Portal 1 не как изображение, а как 3D-сцену с объектами, координатами, геометрией, коллизиями и связями между объектами.**

> **Принцип:** `GAME STATE → WORLD MODEL → SPATIAL REASONING → PLANNING → ACTION`  
> **Не:** `SCREENSHOT → IMAGE CLASSIFICATION → GUESS → ACTION`

Computer Vision НЕ является центральным компонентом. Скриншоты используются только для GUI detection (loading, death, menu).

---

## Архитектура

```
PORTAL 1
  ↓
GAME STATE EXTRACTION (GameStateProvider)
  ↓
3D WORLD MODEL (WorldModel)
  ↓
PERCEPTION / INTERPRETATION
  ↓
GOAL PLANNER
  ↓
ACTION PLANNER
  ↓
INPUT CONTROLLER
  ↓
PORTAL 1

Feedback Loop:
OBSERVE WORLD → UPDATE WORLD MODEL → CHECK GOAL → PLAN ACTION → EXECUTE ACTION → OBSERVE RESULT → UPDATE WORLD MODEL
```

### Модули

1. **GameStateProvider** - извлечение структурированных данных из игры
   - `BSPProvider` - парсит .bsp файлы, даёт static geometry (стены, пол, потолок, portalable surfaces)
   - `SARProvider` - использует SourceAutoRecord plugin (рекомендуемый для runtime)
   - `ConsoleProvider` - парсит консоль игры (getpos, ent_text, cl_showents)
   - `MemoryProvider` - читает память процесса (требует offsets)
   - `MockProvider` - синтетические данные для тестов
   - `AggregatedProvider` - объединяет BSP (static) + SAR (dynamic)

2. **WorldModel** - центральная 3D сцена
   - Player, Rooms, Surfaces, Objects, InteractiveObjects, Portals, Doors, Goals, Connections, Hazards
   - Каждый объект в мировых координатах

3. **Spatial Reasoning** - пространственный анализ
   - Raycast(origin, direction), Trace(from, to), IsPathClear(from, to)
   - GetSurface(point), CanPlacePortal(point, normal)
   - What is left/right/front/behind player?
   - Where is nearest cube? Is obstacle between?
   - All computed from 3D model, not guessed from image

4. **Portal System** - моделирование порталов
   - Position, normal, orientation, linked portal, surface, active state
   - Transform: Position A → Portal A → Portal B → Position B
   - Calculates exit position, orientation, velocity, safe exit

5. **Navigation** - граф достижимости
   - NODE = reachable position / area
   - EDGE = walk, jump, drop, portal, door, button
   - A* pathfinding, dynamic update when doors open or portals placed

6. **Object Relationships** - граф зависимостей
   - Button requires Cube, Door controlled_by Button, Exit behind Door
   - Dependency resolution for puzzle solving

7. **Planner**
   - GoalPlanner: определяет текущую цель (reach_exit, get_cube, activate_button)
   - ActionPlanner: создаёт план из абстрактных действий (MoveTo, PickUp, PlacePortal, etc.)

8. **Action Executor**
   - Translates abstract actions to concrete inputs (W/A/S/D, mouse, E)
   - Movement uses 3D info with PID correction, not "W for 4 seconds"

9. **Recovery** - обработка сбоев
   - Detects stuck, cannot pass, wrong portal, death, lost object
   - Stop → Update WorldModel → Determine cause → Replan → Alternative path

10. **GUI / Debug**
    - Web GUI with Three.js 3D view
    - Shows Player, Walls, Cubes, Buttons, Doors, Portals, Nav Graph, Current Path
    - START/PAUSE/STOP controls

---

## Исследование: Как получить данные из Portal 1

Подробно в [docs/research.md](docs/research.md)

### Entity List
- **Console:** `cl_showents`, `report_entities`, `ent_text`, `ent_bbox`
- **SAR:** `sar_find_ents <filter>`, `sar_find_ent <index>`, `sar_dump_server_datamap`
- **Memory:** найти `client.dll + entityListOffset`, итерировать по указателям
- **Custom Plugin:** написать DLL с `IServerPluginCallbacks`, итерировать `gpGlobals->maxEntities`

### Player State
- `getpos` → `setpos x y z; setang pitch yaw roll`
- `cl_showpos 1` - HUD
- SAR: `sar_hud_player_info`
- Memory: LocalPlayer base + offsets (m_vecOrigin, m_angRotation, m_vecVelocity, m_fFlags)
- Plugin: `UTIL_GetLocalPlayer()`

### World Geometry / BSP
- BSP файл: `portal/maps/testchmb_a_00.bsp` (VBSP v20)
- Lumps: 0 Entities, 1 Planes, 3 Vertexes, 7 Faces, 6 Texinfo, 2 Texdata, 43 TexdataStringData, 29 PhysCollide
- Парсинг даёт стены, пол, потолок, portalable surfaces (по материалу)
- Portalable материалы: `concrete/concrete_modular_*`, `metal/metal_modular_*` с флагом `%noportal 0`
- Инструменты: `srctools`, `Galaco/bsp`, `BSPSource`

### Raycasts / Traces
- Source Engine: `IEngineTrace::TraceRay`, `UTIL_TraceLine`
- `trace_t` содержит startpos, endpos, fraction, m_pEnt, plane.normal, surface.flags
- В Python: реализовать свой raycast против BSP + entity AABB (Möller–Trumbore)
- Portalable check: `tr.surface.flags & SURF_NOPORTAL`

### Portal Entities
- Класс `CProp_Portal` (prop_portal): m_vecOrigin, m_angRotation, m_bActivated, m_bIsPortal2, m_hLinkedPortal, m_vForward/right/up
- Трансформация: `ExitPosition = PortalB.Transform * inverse(PortalA.Transform) * EntryPosition`

### Buttons, Cubes, Doors
- Cube: `prop_weighted_cube` / `prop_physics` - m_vecOrigin, m_angRotation, m_vecVelocity, m_bHeld
- Button: `prop_button` - m_bPressed, m_hUseEntity, connections OnPressed→door.Open
- Door: `func_door` - m_eDoorState (0 closed, 1 opening, 2 open, 3 closing)
- I/O система из Entities lump

---

## Установка

```bash
pip install -r requirements.txt
# Для GUI:
pip install fastapi uvicorn
# Для memory reading (Windows):
pip install pymem
# Для input control:
pip install pynput
```

### SourceAutoRecord (рекомендуется для реальной игры)

1. Скачать SAR: https://github.com/p2sr/SourceAutoRecord/releases
2. Поместить `sar.dll` (Windows) или `sar.so` (Linux) в папку Portal 1
3. В игре консоль: `plugin_load sar`
4. Команды: `sar_find_ents`, `getpos`, `cl_showpos 1`

---

## Использование

### Диагностические тесты (12 тестов)

```bash
python main.py --test
# или
python -m src.tests.test_runner
```

Тесты:
1. Получить позицию игрока
2. Получить список entities
3. Определить cube и координаты
4. Определить button и состояние
5. Определить стены / collision geometry
6. Сделать raycast
7. Определить portalable surface
8. Построить Navigation Graph
9. Переместить игрока из A в B
10. Поставить портал на заданную поверхность
11. Проверить portal traversal
12. Решить простую тестовую комнату

Каждый тест выводит полученные данные.

### Запуск агента

```bash
# Без GUI, 10 итераций с MockProvider
python main.py

# С GUI (3D debug view)
python main.py --gui
# Открыть http://localhost:8000
# Видно: Player, Walls, Cubes, Buttons, Doors, Portals, Nav Graph, Path

# С реальной игрой (пример)
# 1. Запустить Portal 1 с SAR
# 2. В коде main.py использовать AggregatedProvider с BSPProvider + SARProvider
```

### GUI Debug

- **START/PAUSE/STOP** - управление агентом
- **Current Goal** - текущая цель
- **Current Plan** - план действий
- **Current Action** - выполняемое действие
- **Player Position/Rotation** - позиция игрока
- **Visible Entities** - видимые сущности
- **World Model** - полная модель мира
- **3D View** - Three.js рендер:
  - Зеленый - Player
  - Серый/синий - Walls (синий = portalable)
  - Оранжевый - Cubes
  - Красный/зеленый - Buttons (зеленый = pressed)
  - Коричневый/зеленый - Doors
  - Синий/оранжевый - Portals + линия связи
  - Белый - Nav Nodes, синий - Nav Edges, желтый - Current Path

---

## Структура проекта

```
PORTAL1-BOT/
├── docs/
│   ├── research.md          # Исследование методов извлечения данных
│   └── architecture.md      # Детальная архитектура
├── src/
│   ├── game_state/
│   │   ├── provider.py      # Abstract GameStateProvider
│   │   └── implementations/
│   │       ├── bsp_provider.py       # BSP парсер
│   │       ├── sar_provider.py       # SAR plugin
│   │       ├── console_provider.py   # Console parsing
│   │       ├── memory_provider.py    # Memory reading
│   │       ├── mock_provider.py      # Mock for tests
│   │       └── aggregated_provider.py # Combines BSP + SAR
│   ├── world_model/
│   │   ├── vector.py        # Vector3, QAngle, Bounds
│   │   ├── entities.py      # Cube, Button, Door, etc.
│   │   ├── surface.py       # Surface, Room, portalable check
│   │   ├── portal.py        # Portal transformation
│   │   └── model.py         # WorldModel
│   ├── spatial/
│   │   ├── raycast.py       # Raycast, Trace, IsPathClear, CanPlacePortal
│   │   ├── queries.py       # Spatial reasoning (left/right/front/etc)
│   │   └── collision.py     # Collision detection
│   ├── navigation/
│   │   ├── graph.py         # NavNode, NavEdge, NavigationGraph, A*
│   │   └── builder.py       # Builds graph from WorldModel
│   ├── planning/
│   │   ├── object_relationships.py  # Button requires Cube, etc.
│   │   ├── goal_planner.py          # Determines current goal
│   │   ├── puzzle_solver.py         # Creates plan from goal
│   │   └── recovery.py              # Detects failures, recovery
│   ├── action/
│   │   ├── controller.py    # InputController (pynput, mock)
│   │   └── executor.py      # Executes abstract actions
│   ├── perception/
│   │   └── interpretation.py # Converts raw data to semantic WorldModel
│   ├── gui/
│   │   └── app.py           # FastAPI + Three.js debug GUI
│   ├── tests/
│   │   └── test_runner.py   # 12 diagnostic tests
│   └── agent.py             # Full Portal Agent main loop
├── main.py                  # Entry point
├── requirements.txt
└── README.md
```

---

## Порядок разработки (итеративно)

1. ✅ GameStateProvider (BSP + SAR + Mock)
2. ✅ WorldModel
3. ✅ SpatialQuerySystem (raycast, trace)
4. ✅ Navigation (graph builder + A*)
5. ✅ ObjectRelationships + Planner
6. ✅ ActionExecutor + InputController
7. ✅ Recovery
8. ✅ Full Portal Agent
9. ✅ GUI with 3D debug view

Каждый модуль тестируемый независимо.

---

## Примеры

### Получить позицию игрока

```python
from src.game_state.implementations.mock_provider import MockProvider
provider = MockProvider()
player = provider.get_player_state()
print(player.position)  # Vector3(0, 0, 20)
```

### Raycast

```python
from src.spatial.raycast import SpatialRaycaster
raycaster = SpatialRaycaster(provider)
hit = raycaster.raycast(origin, direction, max_dist=1000)
if hit.hit:
    print(f"Hit {hit.entity_id or hit.surface_id} at {hit.position}")
```

### Spatial Queries

```python
from src.spatial.queries import SpatialQuerySystem
queries = SpatialQuerySystem(world_model, raycaster)
cube = queries.get_nearest_cube()
print(f"Nearest cube at {cube.position}, distance {queries.get_distance(player, cube)}")
print(f"Is obstacle between? {queries.is_obstacle_between(player.position, cube.position)}")
```

### Navigation

```python
from src.navigation.builder import NavigationGraphBuilder
builder = NavigationGraphBuilder(world_model, raycaster)
graph = builder.build()
path = graph.find_path(start, goal)
```

### Planning

```python
from src.planning.goal_planner import GoalPlanner
from src.planning.puzzle_solver import ActionPlanner

goal_planner = GoalPlanner(world_model, relationship_graph)
goal = goal_planner.get_current_goal()  # e.g., get_cube

planner = ActionPlanner(world_model, spatial_queries, nav_graph, relationship_graph, raycaster)
plan = planner.plan(goal)
# [MoveTo(cube), PickUp(cube), MoveTo(button), Drop(cube), ...]
```

### Portal Transformation

```python
blue = world_model.portals[blue_id]
orange = world_model.portals[orange_id]
exit_pos = blue.transform_position_to_linked(entry_pos, orange)
exit_vel = blue.transform_direction_to_linked(entry_vel, orange)
```

---

## Главное требование (выполнено)

> Не делать "AI, который смотрит на экран и угадывает происходящее".  
> Делать "AI, который получает структурированную информацию о 3D-игровом мире и рассуждает внутри этой модели".

- ✅ GAME STATE → WORLD MODEL → SPATIAL REASONING → PLANNING → ACTION
- ✅ Player position, entity list, collision geometry из игры, не из скриншотов
- ✅ BSP parsing для стен, пола, потолка, portalable surfaces
- ✅ Raycast / traces для пространственного анализа
- ✅ Portal system с трансформацией
- ✅ Navigation graph с portal edges
- ✅ Object relationships (Button requires Cube, Door controlled_by Button)
- ✅ 3D debug view

---

## Дальнейшее развитие

- [ ] Реализовать Custom Server Plugin (C++) для 100% надёжного извлечения данных
- [ ] Интеграция с SAR HTTP endpoint для live данных
- [ ] BSP parser с полной поддержкой edges/surfedges для точной геометрии
- [ ] VPhysics collision (physcollide lump)
- [ ] Более сложное планирование с учётом физики кубов и импульса через порталы
- [ ] Обучение с подкреплением поверх WorldModel (а не пикселей)
- [ ] Прохождение всех тестовых камер Portal 1

---

## Лицензия

MIT
