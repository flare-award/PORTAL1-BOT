# Исследование: Получение структурированных данных из Portal 1 / Source Engine

Дата: 2026-09-07
Цель: определить, какие данные о 3D-мире можно получить из Portal 1 без использования Computer Vision как основного источника.

---

## 1. Архитектура Source Engine (Portal 1 - build 3420 / 5135)

Portal 1 построен на ветке Source Engine 2007 (Orange Box). Ключевые DLL:

- `server.dll` - логика сущностей, физика, геймплей
- `client.dll` - рендер, предсказание, HUD
- `engine.dll` - BSP, PVS, трассировка, консоль

В памяти игры существует несколько центральных структур:

### 1.1 Entity List

```cpp
// server.dll
CGlobalEntityList *g_pEntityList;
// или
CBaseEntityList *g_EntList;
```

В Portal 1 entity list - это массив edict_t / CBaseEntity* размером до 2048 (MAX_EDICTS).

Каждая сущность:
- `m_iClassname` - имя класса (например `prop_weighted_cube`)
- `m_vecOrigin` - Vector (x,y,z) - абсолютная позиция
- `m_angRotation` - QAngle
- `m_vecVelocity` / `m_vecAbsVelocity`
- `m_Collision.m_vecMins`, `m_vecMaxs` - AABB
- `m_Collision.m_usSolidFlags`, `m_nSolidType`
- `m_iHealth`, `m_lifeState`
- `m_hOwnerEntity`, `m_hGroundEntity`
- datamap properties (SendProp / DataMap)

Клиентская копия: `cl_entitylist` + `C_BaseEntityList` в `client.dll`

**Способы получить:**

1. **Console**: `cl_showents`, `report_entities`, `ent_text <name>`, `ent_bbox <name>`, `cl_pdump`, `status`
2. **SAR (SourceAutoRecord)**: `sar_find_ents <substring>` выводит список entity index + classname + position. `sar_find_ent <index>` детально. `sar_dump_server_datamap` - все поля класса.
3. **Memory reading**: найти `client.dll + entityListOffset`, итерировать по указателям. Инструменты: Cheat Engine + pointer scan, GH Entity List Finder. Пример для Orange Box:
   - LocalPlayer: `client.dll + 0x4C6708` (пример, версия-зависимо)
   - EntityList: `client.dll + 0x4D3904` (для Portal 1 нужно найти заново)
   - Offsets внутри entity: `m_vecOrigin = 0x138`, `m_angRotation = 0x128`, `m_vecVelocity = 0xE4` (уточняется через datamap dump)
4. **Custom Server Plugin**: написать DLL реализующую `IServerPluginCallbacks`, загружаемую через `plugin_load`. Внутри:
   ```cpp
   // Получить интерфейсы
   IServerGameEnts *gameents = (IServerGameEnts*)interfaceFactory("IServerGameEnts001", NULL);
   IVEngineServer *engine = ...
   // Итерация
   for(int i=0; i<gpGlobals->maxEntities; ++i){
     edict_t *ed = engine->PEntityOfEntIndex(i);
     if(!ed || ed->IsFree()) continue;
     CBaseEntity *ent = gameents->EdictToBaseEntity(ed);
     // читать datamap
   }
   ```
   Этот метод 100% надёжен и не требует reverse engineering.

### 1.2 Player State

Класс: `CPortal_Player : CBasePlayer`

Поля (из Source SDK 2007 `c_baseplayer.h` + `portal_player.h`):

- `m_vecOrigin` - позиция ног
- `m_vecViewOffset` - смещение глаз (обычно 0,0,64)
- `EyePosition() = m_vecOrigin + m_vecViewOffset`
- `m_angEyeAngles` - углы взгляда (pitch,yaw,roll)
- `m_vecVelocity[3]`
- `m_fFlags` - FL_ONGROUND (1), FL_DUCKING (2), etc.
- `m_lifeState` - 0 alive, 2 dead
- `m_hActiveWeapon`, `m_hPortalGun`
- `m_bHeldObject` - держит ли куб

Получение:

- Консоль: `getpos` -> `setpos x y z; setang pitch yaw roll`
- `cl_showpos 1` - HUD с pos/ang/vel
- SAR: `sar_hud_player_info 1` + `sar_player_hud` показывает pos, vel, flags
- Memory: LocalPlayer base + offsets
- Plugin: `UTIL_GetLocalPlayer()` или `UTIL_PlayerByIndex(1)`

### 1.3 Entity Classes в Portal 1

Список критичных для агента:

```
player
prop_portal                    - портал
prop_weighted_cube             - куб (в Portal 1 это prop_physics с моделью metal box)
prop_physics                   - физический объект (куб)
prop_button                    - кнопка для куба (floor button)
func_button                    - кнопка настенная
prop_floor_button              - Portal 2 name, в Portal 1 - prop_button
prop_floor_cube_button
func_door
prop_door_rotating
trigger_portal_cleanser        - поле эмансипации
trigger_hurt
trigger_gravity
npc_portal_turret_floor        - турель
prop_energy_ball               - энергетический шар
prop_laser_catcher / prop_laser_relay
info_player_start
info_target
func_brush
func_detail
worldspawn
```

Получить полный список: `dumpentityfactories` в консоли (выводит все зарегистрированные классы из server.dll)

### 1.4 Bounding Box / Collision Geometry

- `CCollisionProperty`: `m_vecMins`, `m_vecMaxs`, `m_nSolidType`, `m_usSolidFlags`
- `VPhysics`: `IPhysicsObject *VPhysicsGetObject()` -> `GetCollide()` -> `physcollide_t`
- `physcollide` lump в BSP (Lump 29) содержит convex hulls
- `CM_BoxTrace`, `UTIL_TraceHull` для проверки коллизий

Получение:
- `ent_bbox <entity>` рисует AABB
- `vcollide_wireframe 1` рисует vphysics
- `showtriggers_toggle`
- Memory: читать collision property
- BSP parser: извлечь brush sides для статики

### 1.5 Map Geometry / BSP Data

BSP файл Portal 1: `portal/maps/testchmb_a_00.bsp` (лежит в `portal/maps/` или в VPK)

Формат VBSP version 20 (Source 2007)

Lumps (см. https://developer.valvesoftware.com/wiki/Source_BSP_File_Format):

- 0: Entities - текстовый список всех entities в карте (keyvalues). Содержит origin, angles, classname, connections. Можно парсить без загрузки игры!
- 1: Planes
- 2: Texdata
- 3: Vertexes
- 5: Nodes
- 6: Texinfo
- 7: Faces - полигоны мира
- 10: Leafs
- 14: Models (brush models)
- 18: Brushes
- 19: Brushsides
- 29: PhysCollide
- 35: GameLump (static props)
- 40: Pakfile (embedded zip)
- 43: TexdataStringData

**Что можно извлечь:**

- Статические стены/пол/потолок: из Faces + Planes + Vertexes
- Portalable surfaces: по материалу. В Portal 1 portalable - это материалы `concrete/concrete_modular_*`, `metal/metal_modular_*` с флагом `%noportal 0`. Не-portalable: `metal/black_wall_metal`, `glass`, etc. Можно проверить `surfaceprop` или список материалов в `portal/scripts/surfaces.txt` / `portal/materials/`
- Trigger volumes: из Entities lump (classname `trigger_*` + `origin` + `model` -> brush index)
- Spawn points, buttons, doors: из Entities lump

**Инструменты парсинга:**

- Python: написать парсер lumps (struct), есть библиотека `bsp_tool`, `python-valve`, `srctools`
- Go: `Galaco/bsp`
- BSPSource - декомпилятор в VMF
- `srctools.bsp` (Python) уже умеет парсить Portal 1 BSP

### 1.6 Traces / Raycasts

Source Engine имеет `IEngineTrace`:

```cpp
class IEngineTrace {
  void TraceRay(const Ray_t &ray, unsigned int fMask, ITraceFilter *filter, trace_t *trace);
}
```

`trace_t` содержит:
- `startpos`, `endpos`
- `fraction` - 0..1, где произошло столкновение
- `allsolid`, `startsolid`
- `m_pEnt` - сущность с которой столкнулись
- `plane.normal`, `plane.dist` - нормаль поверхности
- `surface.flags`, `surface.name`

**Способы получить:**

1. Внутри server plugin: `UTIL_TraceLine(vecStart, vecEnd, MASK_SOLID, pIgnore, COLLISION_GROUP_NONE, &tr);`
2. SAR: `sar_trace_record`, `sar_trace_reveal`, `sar_trace_playback` - но это для TAS
3. Собственная реализация raycast против:
   - BSP геометрии (faces + planes)
   - Entity AABB (быстрый broadphase) + OBB если нужно
   - Portalable check: `tr.surface.flags & SURF_NOPORTAL`

Для Python агента: реализовать `Raycast(origin, dir)` используя:
- Парсинг BSP faces в треугольники
- Möller–Trumbore intersection
- Проверка AABB entities
- Возврат `HitResult`

### 1.7 Portal Entities

В Portal 1 класс `CProp_Portal` (prop_portal)

Ключевые поля (из `prop_portal_shared.h`):

- `m_vecOrigin`
- `m_angRotation`
- `m_bActivated` - активен ли
- `m_bIsPortal2` - false=blue, true=orange
- `m_hLinkedPortal` - EHANDLE на связанный портал
- `m_plane_Origin` - plane origin
- `m_vForward`, `m_vRight`, `m_vUp` - ориентация
- `m_model` - модель портала

Получение:
- `ent_text prop_portal` покажет все поля
- SAR: `sar_find_ents prop_portal`
- Memory: найти prop_portal entities, читать linked handle

Трансформация через портал:
```
WorldToPortalLocal = portal.InverseTransform
PortalAToPortalB = linkedPortal.Transform * inverse(portalA.Transform)
ExitPosition = PortalB.Transform * (PortalA.InverseTransform * EntryPosition)
ExitVelocity = PortalB.TransformDirection * (PortalA.InverseTransformDirection * EntryVelocity)
```

### 1.8 Buttons, Cubes, Doors

- **Cube**: `prop_physics` или `prop_weighted_cube`
  - `m_vecOrigin`, `m_angRotation`, `m_vecVelocity`
  - `m_bHeld` / `m_hHeldByPlayer`
  - `m_Collision`
  - Проверка на кнопке: distance to button < threshold + button.m_bPressed

- **Button**: `prop_button` / `prop_floor_button`
  - `m_vecOrigin`
  - `m_bPressed` (bool)
  - `m_bDisabled`
  - `m_hUseEntity` - что на ней стоит (куб)
  - Связи: `OnPressed -> door.Open`, `OnUnPressed -> door.Close` (из Entities lump I/O)

- **Door**: `func_door` / `prop_door_rotating`
  - `m_vecOrigin`, `m_angRotation`
  - `m_eDoorState` (0 closed, 1 opening, 2 open, 3 closing)
  - `m_bLocked`

I/O система Source: каждая сущность имеет outputs (OnPressed, OnUnPressed, etc.) которые хранятся в Entities lump как `connections`.

### 1.9 Physics Objects

- `CPhysicsProp` / `prop_physics`
- `VPhysicsGetObject()` -> `IPhysicsObject`
- Поля: mass, inertia, velocity, angular velocity

Для агента достаточно: position, velocity, bounds, held state.

### 1.10 Trigger Volumes

- `trigger_multiple`, `trigger_once`, `trigger_portal_cleanser`, `trigger_hurt`
- В BSP: brush model с `contents = CONTENTS_TRIGGER`
- В Entities lump: `origin`, `model`, `mins`, `maxs` (или brush)
- Можно парсить как AABB и проверять `player inside?`

### 1.11 Visibility / PVS

- `leafs`, `clusters`, `visdata` lumps
- `engine->GetClusterForOrigin()`, `engine->CheckOriginInPVS()`
- Для агента: упрощённо, использовать raycast для visibility, или PVS для оптимизации

---

## 2. Сравнение методов извлечения данных

| Метод | Доступные данные | Сложность | Надёжность | Требует модификации игры | Работает в Portal 1 |
|-------|------------------|-----------|------------|--------------------------|---------------------|
| **Console parsing** | player pos (getpos), entity list (cl_showents), bounding boxes | Низкая | Средняя | Нет | Да, но ограничено |
| **SAR Plugin** | entity list, pos, ang, vel, datamap, traces, portal state, player state | Низкая (готовый plugin) | Высокая | Да (plugin_load sar) | Да, поддерживается с v1.8+ |
| **Memory Reading** | всё (entity list, player, collision) | Высокая (offsets) | Низкая (версия-зависимо) | Нет, но нужен external process | Да, но нужны offsets |
| **Custom Server Plugin (Source SDK)** | всё, включая traces, I/O, collision, portalable check | Средняя (C++) | Очень высокая | Да (скомпилировать DLL) | Да, ideal |
| **BSP Parsing** | static geometry, walls, floors, portalable surfaces, triggers, entity spawns | Низкая (Python) | Высокая | Нет (чтение файлов) | Да |
| **VPK + Material parsing** | portalable materials, models | Низкая | Высокая | Нет | Да |

**Рекомендуемая комбинация для агента:**

1. **BSP Provider** - базовый уровень: загружает карту, даёт стены, пол, потолок, portalable surfaces, триггеры, стартовые позиции entities. Работает offline без запущенной игры. Источник истины для static geometry.
2. **SAR Provider** - primary runtime: подключается к игре через `sar` console interface или через чтение логов / named pipe. Даёт live entity list, player state, portal state. SAR уже умеет `sar_find_ents`, `sar_hud_player_info`, `sar_inspection`.
3. **Console Provider** - fallback: парсит вывод консоли `getpos`, `ent_text`, `cl_showents`. Можно автоматизировать через RCON или чтение `console.log`.
4. **Memory Provider** - advanced: если SAR недоступен, читает память процесса через `pymem`. Требует обновления offsets при патчах.
5. **Custom Plugin Provider** - ultimate: написать свой `portal_bot.dll` который экспортирует JSON по TCP/HTTP/shared memory. Самый чистый способ, но требует C++ разработки.

Для данной реализации мы сделаем архитектуру, где `GameStateProvider` - интерфейс, а реализации можно переключать.

---

## 3. Детали по каждому типу данных

### 3.1 Как получить entity list? 
- SAR: `sar_find_ents ""` -> список всех
- Console: `report_entities` (только count), `cl_showents` (только class+index)
- Memory: найти g_pEntityList, итерировать
- Plugin: `gpGlobals->maxEntities` + `PEntityOfEntIndex`

### 3.2 Координаты entities?
- Все методы дают `m_vecOrigin` Vector. В SAR вывод включает pos.
- Для brush entities (func_door): origin может быть 0,0,0, а реальная позиция - через `model` -> brush model mins/maxs + origin.

### 3.3 Player position?
- `getpos` -> `setpos 0 0 0` формат: `x y z pitch yaw roll`
- SAR: `sar_hud_player_info` + `cl_showpos`
- Memory: LocalPlayer offset
- Plugin: `CBasePlayer::GetAbsOrigin()`

### 3.4 Collision geometry?
- BSP: PhysCollide lump + Brushes lump
- Console: `vcollide_wireframe 1`, `ent_bbox`, `showtriggers_toggle`
- Memory: `m_Collision + VPhysics`
- Plugin: `modelinfo->GetModelBounds()`, `physcollide->GetAllLumps()`

### 3.5 Raycasts?
- Plugin: `UTIL_TraceLine` / `UTIL_TraceHull` - идеально
- SAR: есть команды трассировки, но не для произвольных лучей (нужно расширение)
- Python: реализовать свой raycast против BSP + AABB entities (делаем в проекте)

### 3.6 Portalable surfaces?
- Материал: проверить `surface->name` содержит `TOOLS/TOOLSNODRAW`? Нет, portalable определяется в `portal` FGD: материалы с `%noportal 0` и surface flag `SURF_NOPORTAL` не установлен.
- В коде: `CProp_Portal::IsPortalableSurface(trace)` - проверяет `tr.surface.flags & SURF_NOPORTAL`, `tr.contents`, `material`
- Можно: парсить `portal/materials/` + `surfaces.txt`, или использовать `UTIL_TraceLine` и проверить `CanPlacePortal`
- SAR: нет прямой команды, но можно вызвать через `ent_fire`? Лучше реализовать в Python проверку по нормали и материалу

### 3.7 State порталов?
- `prop_portal.m_bActivated`, `m_hLinkedPortal`, `m_vForward`
- `ent_text prop_portal` покажет
- SAR: `sar_find_ents prop_portal` + inspection

### 3.8 Map geometry?
- BSP parsing - основной метод
- Также `modelinfo->GetModel()` в plugin

### 3.9 Безопасное взаимодействие?
- Не писать напрямую в память игры для движения (VAC? Portal 1 не имеет VAC в singleplayer, но лучше не патчить)
- Использовать `engine->ClientCommand` для ввода? Или отправлять input через `input` system.
- Для действий: эмулировать клавиатуру/мышь на уровне OS (pynput, pyautogui) - безопасно, как обычный игрок
- Или использовать `CInput` / `IN_*` buttons через plugin

### 3.10 Версия Portal 1
- Steam версия: AppID 400, build 3420 (старый) и 5135 (последний)
- SAR поддерживает оба
- Offsets отличаются между версиями, поэтому лучше использовать SAR или custom plugin, а не hardcoded offsets

---

## 4. Вывод и выбор архитектуры

**Основной принцип: не использовать скриншоты для 3D понимания.**

Доступные данные позволяют построить полноценную 3D модель мира без CV:

- BSP даёт статическую геометрию (стены, пол, потолок, portalable)
- Entity lump даёт стартовые позиции всех интерактивных объектов + I/O связи
- SAR / Plugin даёт live позиции, скорости, состояния кнопок/дверей/порталов, игрока
- Raycast можно реализовать в Python против BSP + entity AABB, или делегировать движку через plugin

**Рекомендуемая архитектура для реализации:**

```
Portal 1 Process
   |
   +-- SAR Plugin (sar.dll) -> console output / file / TCP
   +-- BSP Files (portal/maps/*.bsp) -> Python BSP parser
   +-- Custom Bot Plugin (optional) -> JSON via localhost:27015
   |
   v
GameStateProvider (агрегатор)
   - BSPProvider: static world
   - SARProvider: dynamic entities + player
   - ConsoleProvider: fallback
   - MemoryProvider: fallback
   |
   v
WorldModel (3D scene graph)
   - Player, Rooms, Surfaces, Objects, Portals, Doors, Goals, Connections, Hazards
   |
   v
SpatialQuerySystem (Raycast, IsPathClear, GetSurface, CanPlacePortal, etc.)
   |
   v
NavigationGraph (nodes=reachable positions, edges=movement/portal/jump/door)
   |
   v
ObjectRelationships (Button requires Cube, Door controlled_by Button, etc.)
   |
   v
Planner (Goal -> Plan: MoveTo, PickUp, PlacePortal, etc.)
   |
   v
ActionExecutor (Abstract actions -> W/A/S/D, mouse, E)
   |
   v
InputController (pynput / SendInput)
   |
   v
Portal 1
```

**Что делаем в этом проекте:**

1. Реализуем интерфейсы и структуры данных для всех модулей
2. Реализуем BSP parser для Portal 1 (Entities lump + basic geometry)
3. Реализуем SARProvider и ConsoleProvider с парсингом вывода
4. Реализуем WorldModel с поддержкой всех типов объектов
5. Реализуем Spatial queries с raycast против AABB + BSP
6. Реализуем Navigation graph builder
7. Реализуем Portal system с трансформацией
8. Реализуем Planner и ActionExecutor
9. Реализуем GUI debug с 3D view (Three.js)
10. Реализуем 12 диагностических тестов (с mock данными, так как игра не запущена в sandbox)

Каждый модуль тестируемый независимо.

Если какие-то данные напрямую недоступны (например, точная portalable проверка без движка), предлагаем fallback:
- Проверка по материалу (список portalable материалов из Portal 1)
- Проверка по нормали (только плоские поверхности, угол < 45° от вертикали/горизонтали? На самом деле порталы можно ставить на любые плоские поверхности, кроме указанных как noportal)
- Raycast + проверка что поверхность достаточно большая (bounds > portal size 64x64)

Не заменяем недоступные данные screenshot recognition, а предлагаем альтернативный технический способ (BSP parsing, material check, SAR).

