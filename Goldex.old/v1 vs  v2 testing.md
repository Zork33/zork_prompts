Сделаю из этого прямой план.

---

## 1. Стенд “старый vs новый”

**Идея:** поднимаем два сервиса + две БД, гоняем один и тот же тест-харнес, сравниваем ответы.

Пример (docker-compose, схематично):

```yaml
version: "3.9"
services:
  db_old:
    image: postgres:16
    environment: { POSTGRES_DB: app, POSTGRES_USER: app, POSTGRES_PASSWORD: app }
  db_new:
    image: postgres:16
    environment: { POSTGRES_DB: app, POSTGRES_USER: app, POSTGRES_PASSWORD: app }

  app_old:
    build: ./old
    environment:
      DB_DSN: postgres://app:app@db_old/app?sslmode=disable
    depends_on: [db_old]

  app_new:
    build: ./new
    environment:
      DB_DSN: postgres://app:app@db_new/app?sslmode=disable
    depends_on: [db_new]

  tests:
    build: ./tests
    depends_on: [app_old, app_new]
```

---

## 2. Пустая БД → тестовые данные + миграции

### 2.1. Наполнение БД

1. **Миграции до нужной версии**
    
    - `old`: накатываем все миграции старого кода.
        
    - `new`: накатываем все миграции нового кода.
        
2. **Единый seed** (важно, чтобы данные были идентичны):
    
    - SQL-дамп `seed.sql` (INSERT’ы), общие для обеих БД;
        
    - или скрипт `seed_db.py/seed_db.go`, который по переменной окружения `DB_DSN` наполняет БД.
        
3. В CI/локально:
    
    - `seed_db` запускается для `db_old`, потом для `db_new` — данные совпадают.
        

### 2.2. Тест миграций (DB Migration)

Отдельный слой тестов:

1. Создать БД в состоянии “старый прод”: миграции старой версии + seed / анонимизированный дамп.
    
2. Прогнать миграции новой версии (тот же контейнер `db_new` или временная БД).
    
3. Проверить инварианты:
    
    - количество строк по таблицам;
        
    - не-null поля, внешние ключи;
        
    - специфические бизнес‑проверки (суммы, статусы и т.п.).
        

---

## 3. Параллельное тестирование HTTP и gRPC

### 3.1. Общий принцип

Тест-харнес должен:

1. Сгенерировать/прочитать набор входных данных (кейсов).
    
2. Для каждого кейса:
    
    - сделать запрос в **старый** сервис;
        
    - сделать запрос в **новый** сервис;
        
    - нормализовать ответы (убрать timestamps, id и т.п.);
        
    - сравнить и заассертить идентичность.
        

### 3.2. HTTP-пример (Python, упрощённо)

```python
import requests
import json

OLD = "http://app_old:8080"
NEW = "http://app_new:8080"

def normalize(body: dict) -> dict:
  body = dict(body)
  body.pop("id", None)
  body.pop("created_at", None)
  return body

def check_case(path, payload):
  r_old = requests.post(f"{OLD}{path}", json=payload)
  r_new = requests.post(f"{NEW}{path}", json=payload)

  assert r_old.status_code == r_new.status_code

  body_old = normalize(r_old.json())
  body_new = normalize(r_new.json())

  assert body_old == body_new, (body_old, body_new)

def test_all():
  cases = [
    ("/api/v1/foo", {"x": 1}),
    ("/api/v1/foo", {"x": 2}),
    # ...
  ]
  for path, payload in cases:
    check_case(path, payload)
```

### 3.3. gRPC

Аналогично, но через два клиента:

- сгенерировать stubs;
    
- создать два канала: `old_stub = ServiceStub(grpc.insecure_channel("app_old:9090"))`, `new_stub = ...`;
    
- на каждый кейс вызвать оба и сравнить ответы после нормализации.
    

---

## 4. Coverage + Codecov

### 4.1. Сбор покрытия

Зависит от языка, но общий шаблон:

- **Go**: `go test ./... -coverprofile=coverage.out`
    
- **Python (pytest)**: `pytest --cov=src --cov-report=xml:coverage.xml`
    
- **Java (JUnit)**: Jacoco → `jacoco.xml`
    

Запускать покрытие **внутри контейнера приложения**, когда гонятся тесты (или отдельно для unit/integration).

### 4.2. Интеграция с Codecov

В CI:

1. Шаги:
    
    - поднять docker-compose;
        
    - прогнать тесты, получить `coverage.*`;
        
    - загрузить в Codecov (GitHub Action / codecov uploader).
        
2. Если надо одно покрытие для старого и нового:
    
    - собрать два файла покрытия;
        
    - объединить (для Go — `gocovmerge`, для остального — или Codecov сам сольёт, или собрать конфиг).
        

---

## 5. Минимальный TODO-план

1. **Собрать docker-compose** со старым/новым сервисом и двумя БД.
    
2. **Сделать общий seed БД** (скрипт/SQL) и добавить шаг в CI.
    
3. **Добавить тест миграций** (старое состояние → новые миграции → проверки).
    
4. **Написать дифф‑харнес** для HTTP и gRPC (как выше).
    
5. **Подключить coverage и Codecov** в pipeline.
    

Если скажешь стек (Go/Java/Python/etc.), могу выдать уже почти готовые команды/конфиги под конкретный язык и CI.