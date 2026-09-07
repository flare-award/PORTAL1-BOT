# BSP Parsing - Получение статической геометрии

Portal 1 карты хранятся в формате VBSP (Valve BSP) версии 20.

## Где находятся BSP файлы

```
Steam/steamapps/common/Portal/portal/maps/
  testchmb_a_00.bsp
  testchmb_a_01.bsp
  ...
  escape_00.bsp
```

Или внутри VPK:
```
portal/portal_pak_*.vpk
```

VPK можно распаковать GCFScape или `vpk` tool.

## Формат BSP

Header:
```
struct dheader_t {
    int ident; // 'VBSP' = 0x50534256 little endian
    int version; // 20 для Portal 1
    lump_t lumps[64]; // offset, length, version, fourCC
    int mapRevision;
}
```

Lumps (важные):
- 0: Entities - текстовый список всех entities (keyvalues)
- 1: Planes - плоскости
- 2: Texdata
- 3: Vertexes - вершины
- 5: Nodes - BSP nodes
- 6: Texinfo - texture info
- 7: Faces - грани (полигоны мира)
- 10: Leafs
- 14: Models (brush models)
- 18: Brushes
- 19: Brushsides
- 29: PhysCollide - collision
- 35: GameLump (static props)
- 40: Pakfile (embedded zip)
- 43: TexdataStringData - имена материалов
- 44: TexdataStringTable - индексы имён материалов

Подробно: https://developer.valvesoftware.com/wiki/Source_BSP_File_Format

## Что можно извлечь

### Entities Lump (Lump 0)

Текстовый формат:
```
{
"classname" "worldspawn"
"mapversion" "400"
...
}
{
"origin" "100 200 300"
"angles" "0 90 0"
"classname" "prop_weighted_cube"
"targetname" "cube_1"
}
{
"origin" "0 0 0"
"classname" "prop_button"
"targetname" "button_1"
"connections" "OnPressed door_1,Open,0,0,-1"
}
```

Парсится regex: `\{([^}]*)\}` и `"([^"]+)"\s+"([^"]*)"`

Даёт:
- Стартовые позиции всех entities
- I/O connections (OnPressed -> door.Open)
- Targetnames для связей

### Faces / Planes / Vertexes

Faces - полигоны мира (стены, пол, потолок).

Каждый face:
- planenum - индекс в Planes lump (нормаль + dist)
- texinfo - индекс в Texinfo (материал, флаги)
- area - площадь
- firstedge, numedges - для получения вершин (нужны Edges и Surfedges lumps)

Planes:
```
struct dplane_t {
    Vector normal;
    float dist;
    int type;
}
```

Позиция на плоскости: `pos = normal * dist`

### Texdata / Materials

TexdataStringData содержит все имена материалов как null-terminated строки.

TexdataStringTable - массив offsets в StringData.

Texdata - содержит nameStringTableID, который указывает в StringTable.

Texinfo - содержит texdata индекс и flags.

Пример материала:
```
concrete/concrete_modular_wall
metal/black_wall_metal
tools/toolsnodraw
```

Portalable определяется по материалу (см. surface.py):
- Portalable: `concrete/concrete_modular_*`, `metal/metal_modular_*`
- Non-portalable: `metal/black_wall_metal`, `glass`, `tools/*`

Флаг `SURF_NOPORTAL` в texinfo.flags также указывает non-portalable.

### PhysCollide (Lump 29)

Содержит convex hulls для VPhysics collision.

Формат сложный, но можно парсить для точной collision geometry.

Для простоты, в нашем проекте используем AABB из entities + Faces как приближение.

## Python парсер (упрощённый)

См. `src/game_state/implementations/bsp_provider.py` - полная реализация.

Ключевые части:

```python
def parse_entities_lump(data: bytes):
    text = data.decode('utf-8', errors='ignore')
    entities = []
    pattern = re.compile(r'\{([^}]*)\}', re.DOTALL)
    kv_pattern = re.compile(r'"([^"]+)"\s+"([^"]*)"')
    for match in pattern.finditer(text):
        block = match.group(1)
        ent = {}
        for kv_match in kv_pattern.finditer(block):
            ent[kv_match.group(1)] = kv_match.group(2)
        entities.append(ent)
    return entities

class BSPFile:
    def load(self):
        with open(path, 'rb') as f:
            ident = struct.unpack('i', f.read(4))[0]
            assert ident == 0x50534256
            version = struct.unpack('i', f.read(4))[0]
            lumps = []
            for _ in range(64):
                offset, length, ver, fourcc = struct.unpack('iiii', f.read(16))
                lumps.append((offset, length, ver, fourcc))
            # Read entities
            off, length, _, _ = lumps[0]
            f.seek(off)
            data = f.read(length)
            self.entities_raw = parse_entities_lump(data)
            # ... другие lumps
```

## Использование для бота

```python
from src.game_state.implementations.bsp_provider import BSPProvider
from pathlib import Path

bsp = BSPProvider()
bsp.load_bsp(Path("portal/maps/testchmb_a_00.bsp"))

surfaces = bsp.get_world_geometry()
print(f"Found {len(surfaces)} surfaces")
for surf in surfaces:
    print(f"Surface {surf.id}: pos={surf.position} normal={surf.normal} portalable={surf.portalable} material={surf.material}")

entities = bsp.get_entities()
for ent in entities:
    print(f"Entity {ent.id}: {ent.classname} at {ent.position}")
```

## Portalable Surfaces

В Portal 1 portalable определяется:

1. Материал не в списке non-portalable:
   - `metal/black_wall_metal`
   - `glass/*`
   - `tools/*`

2. Материал в списке portalable:
   - `concrete/concrete_modular`
   - `metal/metal_modular`
   - `plastic/plastic_modular`

3. Флаг `SURF_NOPORTAL` не установлен (проверяется в texinfo.flags)

4. Поверхность достаточно большая (минимум 64x64 для портала)

5. Поверхность плоская (все вершины в одной плоскости)

В коде: `src/world_model/surface.py:is_material_portalable()`

## Ограничения BSP парсинга

- Даёт только статическую геометрию (без динамических entities)
- Не даёт live позиции кубов (они могут двигаться)
- Требует знания формата (версия-зависимо)
- PhysCollide парсинг сложный
- Для динамических entities нужен SAR/Memory/Custom Plugin

Поэтому используем AggregatedProvider: BSP для статики + SAR для динамики.

## Инструменты

- **BSPSource**: https://github.com/ata4/bspsrc - декомпилятор BSP -> VMF (можно посмотреть в Hammer)
- **srctools**: Python библиотека для парсинга BSP, VPK, VMF
  ```bash
  pip install srctools
  from srctools.bsp import BSP
  bsp = BSP("testchmb_a_00.bsp")
  ```
- **Galaco/bsp**: Go библиотека https://github.com/Galaco/bsp
- **GCFScape**: для распаковки VPK
- **Hammer**: официальный редактор карт

## Пример: Найти все portalable стены в карте

```python
bsp = BSPProvider()
bsp.load_bsp("testchmb_a_00.bsp")

portalable = [s for s in bsp.get_world_geometry() if s.portalable]
print(f"Portalable: {len(portalable)}")

# Найти ближайшую portalable стену к игроку
player_pos = Vector3(0,0,0)
closest = min(portalable, key=lambda s: s.position.distance_to(player_pos))
print(f"Closest portalable: {closest.position} normal {closest.normal}")
```
