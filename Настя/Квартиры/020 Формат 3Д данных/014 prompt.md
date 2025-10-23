---
created: 2025-10-22 12:03:28
---
# 014 prompt

Ниже — простой, **LLM‑дружелюбный** формат **AP3D v1.0** (JSON) для описания квартиры. Его хватает, чтобы строить 2D‑проекции (планы/разрезы/фасады) и собирать 3D‑геометрию (экструзии стен, вырезы проёмов, расстановка объектов). Ключи — короткие, значения — явные, без двусмысленностей.

---

## 1) Базовые правила

- **Единицы:** метры. **Точность:** 0.001 м.
    
- **Оси:** правосторонние, **Z — вверх**, XY — плоскость пола.
    
- **Полигоны:** вершины в **CCW** (против часовой). Закрывать не нужно (последняя ≠ первой).
    
- **Ссылки:** все сущности имеют `id`. Вложенные ссылки по `id` или через «ребро комнаты» (`room_id` + `edge_index`).
    
- **Высоты:** `level.elevation_z` — отметка уровня; высота помещения `room.height` от пола уровня.
    
- **Толщина стен:** от осевой линии, `reference_line: "center" | "left" | "right"`. По умолчанию `"center"`.
    

---

## 2) Минимальный состав данных

- `meta` — версия, автор, дата.
    
- `units`, `coord_sys`.
    
- `levels[]` — этажи/уровни (elevation).
    
- `rooms[]` — помещения: полигон XY, высота.
    
- `walls[]` — сегменты с толщиной/высотой, материалом и примыкающими комнатами (необязательно, если удобно генерировать из границ комнат).
    
- `openings{doors[], windows[]}` — проёмы, привязанные к стене или к ребру комнаты.
    
- `objects[]` — мебель/оборудование с позой (позиция + повороты).
    
- `materials{}` — палитра материалов (цвет, текстуры).
    
- `defaults.projections` — параметры сечения плана/разрезов.
    

---

## 3) Пример (компактный)

```json
{
  "meta": { "format": "AP3D", "version": "1.0", "author": "you", "created_at": "2025-10-21" },
  "units": "m",
  "coord_sys": "RH_Z_UP",
  "tolerance": 0.001,

  "levels": [
    { "id": "L1", "name": "Level 1", "elevation_z": 0.0, "default_ceiling_height": 2.70 }
  ],

  "materials": {
    "mat_wall_ext": { "name": "Ext Wall", "color": "#d9d9d9" },
    "mat_wall_int": { "name": "Int Wall", "color": "#eeeeee" },
    "mat_floor":    { "name": "Floor",    "color": "#c8b7a6" },
    "mat_window":   { "name": "Glass",    "color": "#88bbee", "opacity": 0.3 }
  },

  "rooms": [
    {
      "id": "R_LIVING",
      "name": "Living",
      "level_id": "L1",
      "polygon": [[0,0],[6,0],[6,4],[0,4]],
      "height": 2.70,
      "floor_material_id": "mat_floor",
      "tags": ["day"]
    },
    {
      "id": "R_BED",
      "name": "Bedroom",
      "level_id": "L1",
      "polygon": [[6,0],[9,0],[9,4],[6,4]],
      "height": 2.70,
      "floor_material_id": "mat_floor",
      "tags": ["night"]
    }
  ],

  "walls": [
    { "id": "W_ext_S", "level_id": "L1",
      "start":[0,0], "end":[9,0], "height":2.7, "thickness":0.25,
      "material_id":"mat_wall_ext", "reference_line":"center",
      "adjacent_rooms":["R_LIVING","R_BED"]
    },
    { "id": "W_ext_N", "level_id": "L1",
      "start":[0,4], "end":[9,4], "height":2.7, "thickness":0.25,
      "material_id":"mat_wall_ext", "reference_line":"center",
      "adjacent_rooms":["R_LIVING","R_BED"]
    },
    { "id": "W_ext_W", "level_id": "L1",
      "start":[0,0], "end":[0,4], "height":2.7, "thickness":0.25,
      "material_id":"mat_wall_ext", "adjacent_rooms":["R_LIVING"] },
    { "id": "W_ext_E", "level_id": "L1",
      "start":[9,0], "end":[9,4], "height":2.7, "thickness":0.25,
      "material_id":"mat_wall_ext", "adjacent_rooms":["R_BED"] },
    { "id": "W_int_AB", "level_id": "L1",
      "start":[6,0], "end":[6,4], "height":2.7, "thickness":0.12,
      "material_id":"mat_wall_int", "adjacent_rooms":["R_LIVING","R_BED"] }
  ],

  "openings": {
    "doors": [
      {
        "id": "D_entry",
        "target": { "type": "wall_id", "id": "W_ext_S" },
        "position_along_wall_m": 1.20,
        "width": 0.90, "height": 2.10,
        "sill_z": 0.0,
        "swing": { "hinge": "left", "opens_to_room_id": "R_LIVING", "angle_deg": 90 }
      },
      {
        "id": "D_bed",
        "target": { "type": "wall_id", "id": "W_int_AB" },
        "position_along_wall_m": 1.00,
        "width": 0.80, "height": 2.00,
        "sill_z": 0.0,
        "swing": { "hinge": "right", "opens_to_room_id": "R_BED", "angle_deg": 90 }
      }
    ],
    "windows": [
      {
        "id": "WN_bed",
        "target": { "type": "wall_id", "id": "W_ext_N" },
        "position_along_wall_m": 7.00,
        "width": 1.20, "height": 1.20,
        "sill_z": 0.90,
        "material_id": "mat_window"
      }
    ]
  },

  "objects": [
    {
      "id": "OBJ_sofa",
      "category": "sofa",
      "size": [2.0, 0.9, 0.8],
      "pose": { "position":[1.0,1.0,0.0], "rotation_euler_deg":[0,0,90] },
      "room_id": "R_LIVING"
    },
    {
      "id": "OBJ_bed",
      "category": "bed_queen",
      "size": [2.0, 1.6, 0.6],
      "pose": { "position":[7.2,0.6,0.0], "rotation_euler_deg":[0,0,0] },
      "room_id": "R_BED"
    }
  ],

  "defaults": {
    "projections": {
      "plan_cut_height_z": 1.20,
      "section_planes": [
        { "id":"SEC_A", "point":[6,2,1.2], "normal":[1,0,0] }
      ],
      "elevations": [
        { "id":"EL_N", "room_id":"R_BED", "facing_wall_id":"W_ext_N" }
      ]
    }
  }
}
```

---

## 4) Как строить из AP3D

**2D‑план (top/plan):**

1. Взять все `rooms[].polygon`, выполнить триангуляцию — это «чистый пол».
    
2. Построить стеновые тела: для каждого `walls[]` экструзия вдоль оси Z на `height`, толщина — симметрично от оси (или по `reference_line`).
    
3. Сделать вырезы: для каждого `openings.*` вычесть прямоугольный объём (по ширине/высоте и `sill_z`).
    
4. Сечение на высоте `plan_cut_height_z` — линии, которые пересекает плоскость `Z=plan_cut_height_z`.
    

**Разрез/фасад:**

- Плоскость разреза: `point`,`normal`. Отрисовать пересечения геометрии, плюс проекцию дальнего фона с заливкой.
    

**3D‑модель:**

- Пол/потолок: экструзия полигона комнаты на толщины покрытия (опционально).
    
- Стены: экструзия сегментов в призмы; вырезать `openings`.
    
- Двери/окна: при желании — вставить простые параметрические блоки по центру выреза (ориентация вдоль направления стены `start→end`).
    
- Объекты: разместить `objects[]` по `pose`.
    

---

## 5) Ссылки на ребро комнаты (если стен нет)

Можно не заполнять `walls[]`. Тогда проёмы задавайте так:

```json
"target": { "type": "room_edge", "room_id":"R_BED", "edge_index":1 }
```

`edge_index` — индекс ребра полигона (`[v[i]→v[i+1]]`, нумерация от 0). Движение вдоль ребра — слева направо по CCW.

---

## 6) Экспорт в glTF/OBJ (рекомендации)

- Координаты — как есть (метры, Z‑up). Для glTF (Y‑up) выполните поворот сцены: **Swap**: `(x,y,z)_AP3D → (x,z,y)_glTF` или используйте узел‑родитель с трансформом.
    
- Собирать меши по слоям: `Walls_*, Floors, Ceilings, OpeningsCutters (invisible), Objects`.
    
- Материалы конвертируйте в PBR (albedo = `color`, `metalness=0`, `roughness≈0.7`, `opacity` при необходимости).
    

---

## 7) Мини‑схема (валидация, упрощённо)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AP3D v1.0",
  "type": "object",
  "required": ["units","coord_sys","levels","rooms"],
  "properties": {
    "units": { "enum": ["m"] },
    "coord_sys": { "enum": ["RH_Z_UP"] },
    "levels": {
      "type":"array",
      "items": { "type":"object", "required":["id","elevation_z"] }
    },
    "rooms": {
      "type":"array",
      "items": {
        "type":"object",
        "required":["id","level_id","polygon","height"],
        "properties": {
          "polygon": {
            "type":"array",
            "minItems":3,
            "items": { "type":"array", "items": [{ "type":"number" },{ "type":"number" }], "minItems":2, "maxItems":2 }
          }
        }
      }
    }
  }
}
```

---

## 8) Подсказка для LLM (Sora/Claude)

> «Вот JSON AP3D. Построй 3D‑сцену: экструзия стен по `walls`, вырезы по `openings`, полы из `rooms.polygon`, высоты по `height`, план — сечение `Z=plan_cut_height_z`. Координаты в метрах, Z‑up.»

---

### Готово к использованию

- Используйте пример как шаблон.
    
- Если нужны разрезы/фасады — добавляйте в `defaults.projections` секущие плоскости.
    
- Можно расширять: балки/колонны (`beams[]/columns[]`), инженерка (`pipes[]`), текстуры (`texture_uri`).