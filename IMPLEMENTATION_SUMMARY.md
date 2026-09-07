# Implementation Summary - Portal 1 Bot 3D World Model

## Что реализовано

Полностью реализована архитектура по ТЗ:

```
PORTAL 1
↓
GAME STATE EXTRACTION
↓
3D WORLD MODEL
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
```

### 1. Исследование (docs/research.md)

Проведён детальный анализ способов получения данных из Portal 1 / Source Engine:

- **Entity List**: 4 метода (console, SAR, memory, custom plugin)
- **Player State**: getpos, cl_showpos, SAR, memory, plugin
- **Entity Classes**: полный список Portal 1 (prop_weighted_cube, prop_button, func_door, prop_portal, etc.)
- **Bounding Box / Collision**: ent_bbox, vcollide_wireframe, physcollide lump
- **Map Geometry / BSP**: парсинг VBSP v20, lumps, материалы, portalable surfaces
- **Traces / Raycasts**: IEngineTrace::TraceRay, UTIL_TraceLine, реализация в Python
- **Portal Entities**: CProp_Portal поля, трансформация
- **Buttons, Cubes, Doors**: поля и I/O система
- **Physics Objects**: VPhysics
- **Trigger Volumes**: brush models
- **Visibility / PVS**: leafs, clusters

Вывод: все данные доступны без Computer Vision. Рекомендуемая комбинация: BSPProvider (static) + SARProvider (dynamic).

### 2. GameStateProvider

Интерфейс `GameStateProvider` с методами:
- `get_player_state() -> PlayerState`
- `get_entities() -> List[Entity]`
- `get_world_geometry() -> List[Surface]`
- `get_portals() -> List[Portal]`
- `raycast(origin, direction) -> HitResult`
- `trace(from, to) -> TraceResult`
- `is_path_clear(from, to) -> bool`
- `can_place_portal(point, normal) -> (bool, reason)`
- `get_world_model() -> WorldModel`

Реализации:
- **BSPProvider** (`bsp_provider.py`): парсит .bsp файлы, даёт стены, пол, потолок, portalable surfaces, entity spawns. Работает offline. Реализует raycast против плоскостей + AABB.
- **SARProvider** (`sar_provider.py`): использует SourceAutoRecord. Парсит `getpos`, `sar_find_ents`, `ent_text`. Рекомендуемый для runtime. Поддерживает mock injection для тестов.
- **ConsoleProvider** (`console_provider.py`): парсит консоль (cl_showents, report_entities, status). Fallback.
- **MemoryProvider** (`memory_provider.py`): читает память процесса через pymem. Требует offsets, которые можно получить через SAR (`sar_find_server_offset`). Даёт guide по поиску offsets через Cheat Engine.
- **MockProvider** (`mock_provider.py`): синтетическая тестовая камера 512x512 с кубами, кнопками, дверями, турелями, portalable стенами. Для тестов и разработки без игры.
- **AggregatedProvider** (`aggregated_provider.py`): объединяет BSP (static) + SAR (dynamic). Рекомендуемый для full bot.

### 3. WorldModel

Структуры в мировых координатах:

- **Vector3, QAngle, Bounds** (`vector.py`): математика, dot, cross, normalized, distance, AABB
- **Entity** (`entities.py`): id, classname, position, rotation, velocity, bounds, active
  - PlayerState: eye_position, grounded, alive, holding_object_id, flags
  - Cube: held, on_button_id, mass, companion
  - Button: pressed, required_object, connected_door_ids
  - Door: open, locked, connected_button_ids, door_state
  - Turret, ExitDoor, TriggerVolume
- **Surface, Room** (`surface.py`): position, normal, bounds, portalable, material, vertices, area, is_large_enough_for_portal(). Список portalable/non-portalable материалов Portal 1.
- **Portal** (`portal.py`): portal_type (blue/orange), normal, forward/right/up, linked_portal_id, surface_id, active. Методы world_to_local, local_to_world, transform_position_to_linked, transform_direction_to_linked.
- **WorldModel** (`model.py`): player, entities, surfaces, portals, doors, buttons, cubes, turrets, triggers, rooms, connections, exits, goals. Методы get_nearest_cube, get_active_portals, to_dict, summary.

### 4. Spatial Reasoning

- **SpatialRaycaster** (`raycast.py`): raycast, trace, is_path_clear, get_surface_at_point, can_place_portal, what_is_in_front, find_obstacle_between, get_visible_surfaces, find_portal_placement_candidates
- **SpatialQuerySystem** (`queries.py`): отвечает на вопросы:
  - Что слева/справа/спереди/сзади? (raycast с базисом игрока)
  - Где ближайший cube/button/door?
  - Есть ли препятствие между?
  - Можно ли пройти? Можно ли поставить портал?
  - Какая поверхность соединится через портал?
  - На какой высоте объект? Расстояние? Можно ли перенести cube?
  - Все вычисляется из 3D модели, не угадывается по изображению
- **Collision** (`collision.py`): AABB, point in bounds, sphere, colliding entities

### 5. Portal System

В `portal.py`:
- Portal placement candidate scoring
- Transform math: Position A → Portal A → Portal B → Position B
- Velocity transformation
- Safe exit check (в raycaster)
- Выбор геометрически подходящей поверхности (не случайный клик)

### 6. Navigation

- **NavNode, NavEdge, EdgeType** (`graph.py`): node = reachable position, edge types = walk, jump, drop, portal, door, button, elevator, stairs. Cost calculation.
- **NavigationGraph**: add_node, add_edge, find_closest_node, get_neighbors, find_path (A*), to_dict
- **NavigationGraphBuilder** (`builder.py`): строит граф из WorldModel:
  - Nodes из entity positions + floor surfaces sampled on grid
  - Connect if IsPathClear and height diff acceptable
  - Portal edges if active portals linked
  - Door edges requiring door open
  - Update with portals dynamically

### 7. Object Relationships

`object_relationships.py`:
- RelationType: REQUIRES, CONTROLLED_BY, BEHIND, BLOCKS, POWERS, HOLDS, CONNECTED_TO
- RelationshipGraph: add, get_dependencies, get_dependents, resolve_dependency_order (DFS)
- build_from_world_model: из Button.connected_door_ids, Door.connected_button_ids, Exit.behind_door_id, BSP I/O connections, heuristic nearest cube
- Пример: Exit behind Door, Door controlled_by Button, Button requires Cube → [Cube, Button, Door, Exit]

### 8. Planner

- **GoalPlanner** (`goal_planner.py`): определяет текущую цель по приоритету:
  - Если мертв → survive
  - Если exit за закрытой дверью → open_door → activate_button → get_cube
  - Если куб на возвышении → place_portal
  - get_goal_chain: разрешает dependency chain
- **ActionPlanner / Puzzle Solver** (`puzzle_solver.py`):
  - AbstractAction: MoveTo, LookAt, Jump, Crouch, PickUp, Drop, PlacePortal, EnterPortal, PressButton, Wait, Interact, OpenDoor
  - Планы типа:
    - Reach Exit: MoveTo nodes → EnterPortal → MoveTo Exit
    - Get Cube: MoveTo Cube → LookAt → PickUp (с portal если elevated)
    - Activate Button: Get Cube → MoveTo Button → Drop → Wait
    - Place Portal: LookAt surface → PlacePortal blue → LookAt surface → PlacePortal orange → EnterPortal
  - Учитывает nav graph, spatial queries, relationships

### 9. Action Executor

- **InputController** (`controller.py`): abstract + Mock + Pynput implementations. Методы press_key, hold_key, release_key, move_mouse, mouse_click, look_at (вычисляет yaw/pitch delta → mouse movement), move_towards
- **ActionExecutor** (`executor.py`): исполняет AbstractAction с 3D awareness:
  - MoveTo: определить текущую позицию, target, построить путь, повернуть игрока (LookAt), двигаться W с коррекцией, проверять позицию, остановиться при достижении. Не "W for 4 seconds".
  - LookAt: вычислить yaw/pitch к цели, двигать мышь
  - PickUp/Drop: E + обновление WorldModel (held, on_button, button pressed, door open)
  - PlacePortal: LookAt surface → check CanPlacePortal → mouse click left/right → simulate portal creation
  - EnterPortal: MoveTo portal → transform position via portal math → teleport
  - Feedback loop: после каждого действия observe world → check failure → recovery → replan

### 10. Perception

`interpretation.py`: WorldInterpreter конвертирует raw GameStateProvider data в семантический WorldModel:
- Классифицирует entities
- Enrich: cube on button → button pressed → door open
- Build rooms from surfaces
- Determine goals
- Build connections

### 11. Recovery

`recovery.py`: RecoverySystem детектирует:
- Застревание (position history, min movement threshold)
- Смерть (alive false)
- Потерю объекта (cube far from expected)
- Неправильный портал (both on same wall, not linked)
- Невозможность пройти, неправильную траекторию

При проблеме: stop → update WorldModel → determine cause → get_recovery_action → replan.

### 12. Agent

`agent.py`: PortalAgent main loop:
```
OBSERVE WORLD → UPDATE WORLD MODEL → CHECK GOAL → PLAN ACTION → EXECUTE ACTION → OBSERVE RESULT → UPDATE WORLD MODEL
```
Методы observe_world, check_goal, plan_action, execute_action (with world_update_callback), run_iteration, run (max_iterations), get_debug_info.

### 13. GUI

`gui/app.py`: DebugGUI с FastAPI + WebSocket + Three.js:
- START/PAUSE/STOP controls (POST /api/control/{action})
- GET /api/state → debug info JSON
- WebSocket /ws → live updates 10Hz
- Frontend: index.html с Three.js:
  - OrbitControls для камеры
  - Grid, lights
  - Groups: player (green box), walls (gray/blue portalable), cubes (orange), buttons (red/green), doors (brown/green), portals (blue/orange) + linked line, navNodes (white), navEdges (blue), path (yellow)
  - Sidebar: Current Goal, Plan, Action, Player, World Model summary, Nav Graph, Log
- Bind 0.0.0.0 для preview: https://{port}-{sandboxId}.e2b.app

### 14. Tests

`tests/test_runner.py`: 12 диагностических тестов (все passing):

1. Получить позицию игрока - Vector3, eye, rotation, velocity, grounded, alive
2. Получить список entities - id, classname, pos, bounds
3. Определить cube и координаты - pos, rot, vel, bounds, distance to player
4. Определить button и состояние - pressed, connected doors, simulate press
5. Определить стены / collision geometry - surfaces, portalable, material, bounds, area
6. Сделать raycast - forward, down, trace to cube, IsPathClear
7. Определить portalable surface - CanPlacePortal, candidates near player
8. Построить Navigation Graph - nodes, edges, A* path
9. Переместить игрока из A в B - MoveTo with PID, position update
10. Поставить портал на заданную поверхность - PlacePortal, active portals
11. Проверить portal traversal - transform position/velocity, EnterPortal teleport
12. Решить простую тестовую комнату - full agent loop 3 iterations, goal chain, button/door states

Каждый тест выводит полученные данные.

### 15. Docs

- `research.md`: детальное исследование всех методов извлечения данных, сравнение, выбор архитектуры
- `architecture.md`: полная архитектура модулей, API, порядок разработки
- `sar_integration.md`: интеграция с SAR, команды, парсинг, флоу
- `bsp_parsing.md`: формат BSP, lumps, portalable surfaces, примеры кода
- `custom_plugin_example.cpp`: пример C++ server plugin, который экспортирует JSON по UDP/file, самый надёжный метод

### 16. Main

`main.py`: entry point с --gui и --test флагами.

## Соответствие ТЗ

- ✅ Основной принцип: PORTAL 1 → GAME STATE → WORLD MODEL → ... → INPUT → PORTAL 1, не скриншоты
- ✅ GameStateProvider с entity list, positions, rotations, bounds, collision, traces, BSP, player, portals, buttons, cubes, doors, turrets, triggers, physics, visibility
- ✅ WorldModel с Player, Rooms, Surfaces, Objects, Portals, Doors, Goals, Connections, Hazards в мировых координатах
- ✅ Построение пространства: стены, пол, потолок, проходы, соединения, проходимость, portalable, куда ведёт дверь, выше/ниже, видимость - из collision geometry и BSP, не из скриншотов
- ✅ Spatial Reasoning: что слева/справа/спереди/сзади, ближайший cube, препятствие, проходимость, portalable, соединение через портал, высота, расстояние, перенос cube - из 3D модели
- ✅ Collision / Raycast API: Raycast, Trace, IsPathClear, GetSurface, CanPlacePortal
- ✅ Portal System: position, normal, orientation, linked, surface, active, трансформация Position A → Portal A → Portal B → Position B, ориентация, направление, высота, безопасный выход, выбор поверхности геометрически
- ✅ Navigation: NODE=reachable position, EDGE=movement, portal, jump, drop, door, button. Граф ROOM A → CORRIDOR → ROOM B и ROOM A → BLUE PORTAL → ORANGE PORTAL → ROOM C
- ✅ Object Relationships: Button requires Cube, Door controlled_by Button, Exit behind Door, dependency resolution
- ✅ Puzzle Solver: CURRENT WORLD STATE + GOAL → PLAN (Move to Cube, Pick up, Move to Button, Place, Door opens, Move through, Reach Exit и с порталами)
- ✅ Action Executor: абстрактные действия → W/A/S/D, SPACE, CTRL, mouse. MoveTo с 3D info, поворот, движение, проверка позиции, коррекция, стоп при достижении, не "W for 4 seconds"
- ✅ Feedback Loop: OBSERVE → UPDATE → CHECK GOAL → PLAN → EXECUTE → OBSERVE RESULT → UPDATE, не длинные заранее записанные последовательности
- ✅ Recovery: застревание, невозможность пройти, неправильный портал, траектория, смерть, потеря объекта, невозможность действия → stop → update → cause → replan → alternative
- ✅ Computer Vision только как вспомогательный для GUI, меню, loading, death, level transition, не для точного положения cube, стен, комнат, порталов, расстояний, 3D позиции
- ✅ GUI: START/PAUSE/STOP, Current Goal/Plan/Action, Player Pos/Rot, Visible Entities, World Model, Path, Portal Connections, 3D debug view Player, Walls, Cubes, Buttons, Doors, Portals, Navigation Graph, Path
- ✅ Тестирование: 12 диагностических тестов с выводом данных
- ✅ Главное требование: AI получает структурированную информацию о 3D мире и рассуждает внутри модели, а не смотрит на экран и угадывает
- ✅ Перед написанием кода исследована техническая возможность получения данных (research.md)
- ✅ Итеративная разработка: GameStateProvider → WorldModel → Spatial → Navigation → Planner → ActionExecutor → Recovery → Full Agent → GUI, каждый тестируемый независимо

## Как использовать с реальной игрой

1. Установить SAR: скачать sar.dll/so, поместить в Portal/portal/, plugin_load sar
2. Запустить Portal 1, загрузить карту
3. В Python:
   ```python
   from src.game_state.implementations.bsp_provider import BSPProvider
   from src.game_state.implementations.sar_provider import SARProvider
   from src.game_state.implementations.aggregated_provider import AggregatedProvider

   bsp = BSPProvider()
   bsp.load_bsp("portal/maps/testchmb_a_00.bsp")

   sar = SARProvider(console_log_path="portal/console.log")

   provider = AggregatedProvider(bsp, sar)

   agent = PortalAgent(provider)
   agent.run()
   ```

4. Или написать custom plugin по примеру custom_plugin_example.cpp, который будет экспортировать JSON по UDP 27015, и Python будет слушать.

## Ограничения текущей реализации

- MockProvider для тестов, так как в sandbox нет Portal 1
- BSP parser упрощённый (без edges/surfedges для точных вершин, использует аппроксимацию bounds)
- MemoryProvider требует актуальных offsets (можно получить через SAR)
- Для продакшена рекомендуется custom plugin (пример дан)

Но архитектура полностью готова для подключения реальных данных - достаточно заменить MockProvider на AggregatedProvider с BSP + SAR.

## Запуск

```bash
pip install -r requirements.txt
python main.py --test   # 12 тестов
python main.py --gui    # GUI с 3D view на http://localhost:8000
python main.py          # 10 итераций агента
```
