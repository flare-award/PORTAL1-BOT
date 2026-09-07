# Архитектура Portal 1 Bot - 3D World Model Approach

## 1. Общий принцип

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
```

**Запрет:** Computer Vision не является центральным компонентом. Скриншоты используются только для GUI detection (loading, death, menu).

## 2. Модули

### 2.1 GameStateProvider

Интерфейс:

```python
class GameStateProvider:
    def get_player_state() -> PlayerState
    def get_entities() -> List[Entity]
    def get_world_geometry() -> WorldGeometry
    def get_portals() -> List[Portal]
    def raycast(origin, direction, max_dist) -> HitResult
    def trace(from, to) -> TraceResult
```

Реализации:

- `BSPProvider` - парсит .bsp файлы, даёт static geometry + entity spawns. Работает offline.
- `SARProvider` - использует SourceAutoRecord plugin. Парсит вывод `sar_find_ents`, `getpos`, `ent_text`. Рекомендуемый для runtime.
- `ConsoleProvider` - парсит консоль игры через RCON / log file. Fallback.
- `MemoryProvider` - читает память процесса (pymem). Требует offsets.
- `MockProvider` - для тестов, отдаёт синтетические данные.
- `AggregatedProvider` - объединяет BSP (static) + SAR (dynamic).

### 2.2 WorldModel

Структуры в мировых координатах:

```python
@dataclass
class Vector3: x,y,z
@dataclass
class QAngle: pitch,yaw,roll
@dataclass
class Bounds: mins,maxs
@dataclass
class PlayerState: position, rotation, velocity, eye_position, grounded, alive, holding
@dataclass
class Entity: id, classname, position, rotation, velocity, bounds, active
@dataclass
class Cube(Entity): held, on_button
@dataclass
class Button(Entity): pressed, required_object, connected_doors
@dataclass
class Door(Entity): open, locked, connected_buttons
@dataclass
class Surface: id, position, normal, bounds, portalable, material, plane_dist
@dataclass
class Portal(Entity): portal_type (blue/orange), normal, linked_portal, surface, active, forward,right,up
@dataclass
class Turret(Entity): active, firing
@dataclass
class TriggerVolume: id, bounds, trigger_type, active
@dataclass
class Room: id, bounds, surfaces, connections, entities
@dataclass
class WorldModel:
    player: PlayerState
    entities: Dict[id, Entity]
    surfaces: List[Surface]
    portals: List[Portal]
    doors: List[Door]
    buttons: List[Button]
    cubes: List[Cube]
    rooms: List[Room]
    hazards: List[TriggerVolume]
    goals: List[Goal]
    timestamp
```

### 2.3 Spatial Reasoning

API:

```python
def raycast(origin: Vector3, direction: Vector3, max_dist=8192) -> HitResult
def trace(from: Vector3, to: Vector3) -> TraceResult
def is_path_clear(from, to) -> bool
def get_surface(point) -> Surface
def can_place_portal(point, normal, portal_type) -> bool
def what_is_left_of_player() -> List[Entity]
def what_is_in_front(distance) -> HitResult
def get_nearest_cube() -> Cube
def is_obstacle_between(a,b) -> bool
def get_distance(a,b) -> float
def get_height_difference(a,b) -> float
```

Реализация:

- Raycast против BSP faces (Möller-Trumbore) + entity AABB
- Portalable check: material + normal + size + SURF_NOPORTAL flag
- Spatial queries: вычисляются из WorldModel, не из изображения

### 2.4 Portal System

```python
@dataclass
class PortalTransform:
    entry_portal: Portal
    exit_portal: Portal
    def transform_position(pos) -> pos
    def transform_direction(dir) -> dir
    def transform_velocity(vel) -> vel
```

Логика:

- Портал имеет position, normal, forward, right, up, linked_portal
- Трансформация: `exit = linked.Transform * inverse(entry.Transform) * entry`
- Проверка безопасного выхода: raycast вниз от exit, проверка что нет стены
- Выбор поверхности: искать ближайшую portalable поверхность с подходящей нормалью

### 2.5 Navigation

```python
@dataclass
class NavNode: id, position, area_type, room_id
@dataclass
class NavEdge: from_node, to_node, edge_type (walk, jump, drop, portal, door, button), cost

class NavigationGraph:
    nodes: List[NavNode]
    edges: List[NavEdge]
    def build(world_model)
    def find_path(from, to) -> List[NavNode]  # A*
    def update(world_model)
```

Типы edges:

- Walk - обычный проход
- Jump - прыжок
- Drop - падение
- Portal - через портал
- Door - через дверь (требует открытия)
- Button - активация кнопки

Построение:

1. Разбить карту на reachable areas (из BSP leafs или grid sampling)
2. Для каждой area создать node
3. Проверить связность через IsPathClear
4. Добавить portal edges: если есть два активных портала, соединить их области
5. Динамически обновлять при изменении мира (дверь открылась, портал поставлен)

### 2.6 Object Relationships

Граф зависимостей:

```
Button B1 requires Cube C1
Door D1 controlled_by Button B1
Exit E1 behind Door D1
Goal: Reach Exit
 -> Dependency: Door D1 must open
   -> Dependency: Button B1 must activate
     -> Dependency: Cube C1 must be placed on Button B1
       -> Dependency: C1 must be reached
```

Реализация:

```python
@dataclass
class Relationship:
    source_id, target_id, relation_type (requires, controlled_by, behind, blocks)

class RelationshipGraph:
    def add_relationship(...)
    def get_dependencies(goal) -> List[Entity]
    def resolve_order(goal) -> List[Task]
```

Извлекается из:

- BSP Entities lump: I/O connections (`OnPressed -> door.Open`)
- Live state: если куб на кнопке, дверь открыта - infer relationship

### 2.7 Planner

```python
@dataclass
class Goal: type (reach_exit, activate_button, get_cube, place_portal), target_id, target_position

@dataclass
class AbstractAction:
    type: MoveTo, LookAt, Jump, Crouch, PickUp, Drop, PlacePortal, EnterPortal, PressButton, Wait, Interact

class GoalPlanner:
    def get_current_goal(world_model) -> Goal

class ActionPlanner:
    def plan(world_model, goal) -> List[AbstractAction]
```

Пример плана:

```
Goal: Reach Exit
Plan:
1. MoveTo(Cube)
2. PickUp(Cube)
3. MoveTo(Button)
4. Drop(Cube) -> Place on Button
5. Wait(Door opens)
6. MoveTo(Door)
7. MoveThrough(Door)
8. MoveTo(Exit)
```

Сложный план с порталами:

```
1. Identify portalable wall near elevated platform
2. Place Blue Portal on wall
3. Identify floor surface near player
4. Place Orange Portal on floor
5. Enter Orange Portal -> exit Blue Portal
6. Reach elevated platform
7. Obtain cube
...
```

### 2.8 Action Executor

```python
class ActionExecutor:
    def execute(action: AbstractAction) -> bool
    def move_to(position): # PID controller
        - определить текущую позицию
        - определить target
        - построить путь (NavigationGraph)
        - повернуть игрока (LookAt)
        - двигаться W/A/S/D с коррекцией
        - проверять позицию каждый tick
        - остановиться при достижении

    def look_at(position):
        - вычислить yaw/pitch к цели
        - двигать мышь

    def place_portal(type, surface):
        - LookAt(surface.position)
        - проверить CanPlacePortal
        - клик мыши (left=blue, right=orange)
```

Перевод в inputs:

- W/A/S/D - движение
- SPACE - прыжок
- CTRL - приседание
- Mouse movement - поворот
- Mouse buttons - порталы
- E - использование / подбор

Реализация InputController через `pynput` (кроссплатформенно) или `SendInput` (Windows).

### 2.9 Perception / Interpretation

Преобразует сырые данные GameStateProvider в семантический WorldModel:

- Классифицирует entities по classname в Cube/Button/Door/etc.
- Строит Rooms из BSP leafs + порталов
- Определяет Connections между комнатами
- Определяет Hazards (turrets, trigger_hurt, emancipation grid)
- Определяет Goals (exit, buttons)

### 2.10 Feedback Loop

```
OBSERVE WORLD -> UPDATE WORLD MODEL -> CHECK GOAL -> PLAN ACTION -> EXECUTE ACTION -> OBSERVE RESULT -> UPDATE WORLD MODEL
```

Каждое существенное действие проверяется по фактическому состоянию мира. Не выполнять длинные заранее записанные последовательности.

Recovery:

- Обнаружение застревания: если позиция не меняется N секунд, хотя должна
- Невозможность пройти: IsPathClear false
- Неправильный портал: портал не активен после placement
- Смерть: player.alive false
- Потеря объекта: cube not in inventory and not at expected pos

При проблеме:

1. Остановиться
2. Обновить WorldModel
3. Определить причину
4. Пересчитать план
5. Попробовать альтернативу

### 2.11 GUI / Debug

Приложение с:

- START/PAUSE/STOP
- Current Goal, Plan, Action, Player Pos/Rot, Visible Entities, World Model, Path, Portal Connections
- 3D debug view: Player, Walls, Cubes, Buttons, Doors, Portals, Navigation Graph, Current Path

Реализация: Web GUI с Three.js (FastAPI backend + WebSocket для live updates) + Python CLI.

---

## 3. Порядок разработки (итеративно)

1. GameStateProvider (BSP + SAR + Mock)
2. WorldModel
3. SpatialQuerySystem (raycast, trace)
4. Navigation (graph builder + A*)
5. ObjectRelationships + Planner
6. ActionExecutor + InputController
7. Recovery
8. Full Portal Agent
9. GUI

Каждый модуль тестируемый независимо - 12 диагностических тестов.

## 4. Тестирование

- TEST 1: Получить позицию игрока
- TEST 2: Получить список entities
- TEST 3: Определить cube и координаты
- TEST 4: Определить button и состояние
- TEST 5: Определить стены / collision geometry
- TEST 6: Сделать raycast
- TEST 7: Определить portalable surface
- TEST 8: Построить Navigation Graph
- TEST 9: Переместить игрока из A в B
- TEST 10: Поставить портал на заданную поверхность
- TEST 11: Проверить portal traversal
- TEST 12: Решить простую тестовую комнату

Каждый тест выводит полученные данные.

## 5. Технологии

- Python 3.11+
- `srctools` или custom BSP parser
- `pymem` для memory reading (опционально)
- `pynput` для input
- `numpy` для математики
- `fastapi` + `uvicorn` + `websockets` для GUI
- `three.js` для 3D debug view
- `dataclasses`, `typing`

## 6. Безопасность

- Не модифицировать память игры для читов
- Input через OS уровень (как обычный игрок)
- SAR plugin - разрешённый speedrun инструмент, не VAC banned в singleplayer
- Custom plugin - только чтение данных, экспорт через TCP

