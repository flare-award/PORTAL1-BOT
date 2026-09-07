# Интеграция с SourceAutoRecord (SAR) - Рекомендуемый метод

SAR - это speedrun плагин для Portal 1/2, который уже решает большинство задач по извлечению данных.

## Установка SAR

1. Скачать с https://github.com/p2sr/SourceAutoRecord/releases
   - Windows: `sar.dll`
   - Linux: `sar.so`

2. Поместить в папку игры:
   ```
   Portal/portal/
   # или
   Portal 2/portal2/
   ```

3. В игре открыть консоль (`~`) и выполнить:
   ```
   plugin_load sar
   ```

4. Проверка:
   ```
   sar_version
   ```

SAR поддерживает Portal 1 с версии 1.8+.

## Полезные команды SAR для бота

### Entity List

```
sar_find_ents <substring>  - найти entities по подстроке класса
sar_find_ents ""           - все entities
sar_find_ent <index>       - детали entity по индексу
sar_find_ents prop_weighted_cube
sar_find_ents prop_button
sar_find_ents prop_portal
```

Вывод:
```
#  123: prop_weighted_cube - pos: 100.00 200.00 300.00 ang: 0 90 0
```

### Player State

```
cl_showpos 1               - показывает pos/ang/vel в HUD
getpos                     - выводит setpos/setang для копирования
sar_hud_player_info 1      - детальная инфа о игроке
sar_hud_velocity 1
sar_hud_flags 1
```

`getpos` вывод:
```
setpos 123.45 678.90 12.34;setang 0.12 89.45 0.00
```

Парсится regex: `setpos\s+([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+);\s*setang\s+([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)`

### Datamap / Offsets

```
sar_dump_server_datamap <classname>   - все поля класса сервера
sar_dump_client_datamap <classname>
sar_find_server_class <classname>
sar_find_client_class <classname>
sar_find_server_offset <classname> <prop>
sar_find_client_offset <classname> <prop>
```

Пример:
```
] sar_find_server_offset CBaseEntity m_vecOrigin
-> offset 0x138
```

Это позволяет автоматически находить offsets для MemoryProvider без Cheat Engine!

### Traces / Raycasts

```
sar_trace_record
sar_trace_reveal
sar_trace_playback
```

Для TAS, но можно адаптировать для бота.

### Inspection

```
sar_inspection_export
sar_inspection_index <index>
sar_hud_inspection 1
```

Показывает поля выбранной entity в реальном времени.

### Entity I/O

```
sar_show_entinp 1          - показывает entity inputs в консоли
```

Полезно для понимания связей Button -> Door.

## Интеграция SAR с Python ботом

### Метод 1: Чтение console.log

1. В `portal/cfg/autoexec.cfg` добавить:
   ```
   con_logfile console.log
   sar_find_ents_interval 100  // кастомная команда, если добавить в SAR
   ```

2. Python читает файл:
   ```python
   from pathlib import Path
   import re

   log_path = Path("C:/Program Files (x86)/Steam/steamapps/common/Portal/portal/console.log")
   content = log_path.read_text()[-10000:]
   # Парсить getpos, sar_find_ents
   ```

### Метод 2: RCON (если SAR добавить RCON сервер)

SAR можно расширить, добавив HTTP/TCP сервер, который отдаёт JSON.

Пример расширения SAR (C++):
```cpp
// В SAR добавить:
CON_COMMAND(sar_bot_export, "Export game state as JSON") {
    // Собрать все entities
    // Отправить по UDP/TCP
}
```

### Метод 3: Использовать существующие SAR команды в цикле

Python может эмулировать нажатие клавиш для ввода команд в консоль и чтения вывода из `console.log`.

Или использовать `con_logfile` + `exec` для автоматизации.

### Метод 4: Чтение памяти через SAR offsets

SAR даёт offsets, которые можно использовать в MemoryProvider:

```python
# В игре выполнить:
# sar_find_server_offset CBaseEntity m_vecOrigin
# sar_find_server_offset CBaseEntity m_angRotation
# sar_find_client_offset CBasePlayer m_vecVelocity

# Затем в Python:
offsets = {
    "m_vecOrigin": 0x138,  # из SAR
    "m_angRotation": 0x128,
    "m_vecVelocity": 0xE4
}
provider = MemoryProvider(offsets=offsets)
provider.connect()
```

Это самый надёжный способ для MemoryProvider, так как offsets всегда актуальны для текущей версии.

## Пример Python кода для парсинга SAR

```python
import re

GETPOS_RE = re.compile(r'setpos\s+([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+);\s*setang\s+([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)')
SAR_ENTS_RE = re.compile(r'#\s*(\d+):\s*([^\s]+)\s*-\s*pos:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+).*ang:\s*([-\d\.]+)\s+([-\d\.]+)\s+([-\d\.]+)')

def parse_getpos(text):
    m = GETPOS_RE.search(text)
    if m:
        x,y,z,pitch,yaw,roll = map(float, m.groups())
        return Vector3(x,y,z), QAngle(pitch,yaw,roll)
    return None

def parse_sar_ents(text):
    entities = []
    for line in text.splitlines():
        m = SAR_ENTS_RE.search(line)
        if m:
            idx = int(m.group(1))
            classname = m.group(2)
            x,y,z = float(m.group(3)), float(m.group(4)), float(m.group(5))
            pitch,yaw,roll = float(m.group(6)), float(m.group(7)), float(m.group(8))
            entities.append((idx, classname, Vector3(x,y,z), QAngle(pitch,yaw,roll)))
    return entities
```

## Рекомендуемый флоу для реального бота

```
1. Запустить Portal 1
2. plugin_load sar
3. con_logfile 1
4. Запустить Python бота с SARProvider + BSPProvider

Python бот:
- BSPProvider загружает portal/maps/<current_map>.bsp для статики
- SARProvider читает console.log или слушает UDP порт
- Каждые 100ms:
  - Отправляет в консоль "getpos" и "sar_find_ents """ (через файл или pipe)
  - Парсит вывод
  - Обновляет WorldModel
  - Планирует действия
  - Выполняет через pynput
```

## Преимущества SAR подхода

- Не требует reverse engineering offsets (SAR уже нашёл их)
- Работает на всех версиях Portal 1 (SAR поддерживает)
- Легальный speedrun инструмент, не VAC banned в singleplayer
- Даёт доступ к datamap, traces, entity I/O
- Можно расширять SAR своим кодом для экспорта JSON

## Недостатки

- Требует загрузки DLL в процесс игры (plugin_load)
- Нужно парсить текстовый вывод консоли (не бинарный протокол)
- Для идеального решения лучше написать свой plugin (см. custom_plugin_example.cpp)

## Альтернатива: Написать свой SAR-like плагин

Если SAR недостаточно, можно форкнуть SAR или написать свой плагин на основе Source SDK 2013, который будет сразу экспортировать JSON по UDP/TCP, как показано в custom_plugin_example.cpp.

Тогда Python бот просто слушает UDP порт и получает структурированный JSON без парсинга текста.

Это идеальное решение для продакшена.
