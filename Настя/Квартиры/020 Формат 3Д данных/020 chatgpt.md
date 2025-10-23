Ниже — **короткий, однозначный формат JSON** для описания квартиры по плану. Все величины — **абсолютные**, по умолчанию в миллиметрах.

### Конвенции

- Система координат: `origin=[0,0]` внизу-слева; `x` вправо, `y` вверх; высота пола `elevationZero=0`.
    
- Контуры и зоны задаём полигонами (список вершин по часовой стрелке, последняя вершина равна первой).
    
- Проёмы (двери/окна) привязываются к **отрезку стены** `edge=[[x1,y1],[x2,y2]]` и имеют смещение **центра** `offset` в мм от начала отрезка по направлению к его концу.
    

### Поля (обязательно)

- `version`, `units.length`
    
- `coordinateSystem` — оси/нулевые уровни
    
- `outline` — внешний контур квартиры (Polygon)
    
- `entrance` — входная дверь (проём на внешнем контуре)
    
- `zones[]` — функциональные зоны (каждая Polygon)
    
- `balconies[]` — балконы/лоджии (каждая Polygon) + связующая дверь
    
- `openings.doors[]`, `openings.windows[]` — все двери/окна с высотами
    
- `waterPoints[]` — точки воды (х/г/канализация) с координатами и отметками
    
- `dimensions[]` — явные размерные линии (откуда‑куда и значение)
    

---

### Пример JSON

```json
{
  "version": "apartment.v1",
  "units": { "length": "mm" },
  "coordinateSystem": { "origin": [0, 0], "x": "right", "y": "up", "elevationZero": 0 },

  "outline": {
    "type": "Polygon",
    "vertices": [[0,0],[12000,0],[12000,8000],[0,8000],[0,0]]
  },

  "entrance": {
    "id": "door_entrance",
    "edge": [[0,0],[12000,0]],
    "offset": 2000,
    "width": 900,
    "height": 2100,
    "swing": "in",
    "hinge": "left"
  },

  "zones": [
    { "id": "z1", "name": "Прихожая", "polygon": [[0,0],[3500,0],[3500,2500],[0,2500],[0,0]] },
    { "id": "z2", "name": "Кухня‑гостиная", "polygon": [[0,2500],[12000,2500],[12000,8000],[0,8000],[0,2500]] }
  ],

  "balconies": [
    {
      "id": "b1",
      "name": "Балкон",
      "polygon": [[10000,8000],[12000,8000],[12000,9500],[10000,9500],[10000,8000]],
      "accessDoorId": "door_b1"
    }
  ],

  "openings": {
    "doors": [
      {
        "id": "door_b1",
        "edge": [[10000,8000],[12000,8000]],
        "offset": 1000,
        "width": 800,
        "height": 2100,
        "swing": "out",
        "hinge": "right",
        "from": "z2",
        "to": "b1"
      }
    ],
    "windows": [
      {
        "id": "win_liv_1",
        "edge": [[0,8000],[12000,8000]],
        "centerOffset": 3000,
        "width": 1200,
        "height": 1500,
        "sillHeight": 900
      },
      {
        "id": "win_liv_2",
        "edge": [[0,8000],[12000,8000]],
        "centerOffset": 9000,
        "width": 1200,
        "height": 1500,
        "sillHeight": 900
      }
    ]
  },

  "waterPoints": [
    { "id": "wp_cold",  "type": "cold",  "position": [2000,3000], "elevation": 600, "pipeDiameter": 20, "zone": "z2" },
    { "id": "wp_hot",   "type": "hot",   "position": [2050,3000], "elevation": 600, "pipeDiameter": 20, "zone": "z2" },
    { "id": "wp_drain", "type": "sewer", "position": [2025,2950], "elevation":   0, "pipeDiameter": 50, "zone": "z2" }
  ],

  "dimensions": [
    { "id": "overall_length", "type": "linear", "from": [0,0], "to": [12000,0], "value": 12000 },
    { "id": "overall_width",  "type": "linear", "from": [0,0], "to": [0,8000],  "value": 8000 },
    { "id": "entrance_offset","type": "linear", "from": [0,0], "to": [2000,0],  "value": 2000 }
  ]
}
```

### Минимальные проверки

- Все `zones` и `openings` лежат внутри `outline`; балконы соприкасаются контуром с `outline`.
    
- Для каждого проёма: `height > 0`, `width > 0`; для окна: `sillHeight + height` ≤ чистой высоты помещения.
    
- `offset`/`centerOffset` ∈ [0; длина(edge)].
    
- Координаты и размеры выражены в тех же абсолютных единицах, что и `units.length`.
    

Готово. Если нужно — адаптирую под ваш конкретный план (добавим перегородки, больше зон/балконов, уточним размеры).