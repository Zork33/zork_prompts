>сделай питон скрипт с основными операциями по созданию веток и шаблонных файлов для очередного шага.  вообщем все шаги где нужно создавать папки и новые файлы. обяфзательно --help должен быть в скрипте

Вот скрипт, который умеет:

- инициализировать проект (`init-project`);
    
- создавать ветку рассуждений (`create-branch`);
    
- создавать шаг/запуск в ветке с шаблонными файлами (`create-run`).
    

Все команды имеют нормальный `--help`.

````python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Утилита для организации проектов с ИИ:
- создаёт структуру проекта;
- создаёт ветки рассуждений;
- создаёт шаги (runs) с шаблонными файлами.

Примеры:
    python ai_flow.py --help
    python ai_flow.py init-project --project 2025-12-01_my-project
    python ai_flow.py create-branch --project 2025-12-01_my-project --branch A_main
    python ai_flow.py create-run --project 2025-12-01_my-project --branch A_main
"""

import argparse
import datetime
import sys
import re
from pathlib import Path

# ---------- Шаблоны ----------

PROJECT_MD_TEMPLATE = """# {project_name}

Создано: {today}

## 1. Цель проекта

<Опиши, что это за проект и какую задачу вы решаете с помощью ИИ.>

## 2. Критерии успеха

- [ ] Критерий 1
- [ ] Критерий 2
- [ ] Критерий 3

## 3. Контекст

- Основная область: <...>
- Ограничения: <технологии, сроки, ресурсы и т.п.>

## 4. Этапы (черновой план)

1. Сбор и формализация требований.
2. Проработка архитектуры / дизайна.
3. Спецификация реализации и тестов.

"""

PLAN_MD_TEMPLATE = """# План по проекту: {project_name}

## 1. Текущее состояние

- Активная ветка рассуждений: A_main
- Последний шаг (run): A_001 (появится после первого запуска)
- Статус проекта: в работе

## 2. Этапы

### Этап 1. Требования
- [ ] A_001 — первичный сбор требований
- [ ] A_002 — детализация ролей и прав

### Этап 2. Архитектура
- [ ] B_001 — первый вариант архитектуры
- [ ] B_002 — альтернативный вариант

## 3. Бэклог вопросов к ИИ

- [ ] ...
- [ ] ...

"""

JOURNAL_MD_TEMPLATE = """# Журнал работы с ИИ

> Каждому запуску (run) соответствует одна запись в этом журнале.

"""

BRANCH_INFO_TEMPLATE = """# Ветка {branch_id}

## 1. Общие сведения
- Идентификатор ветки: {branch_id}
- Родительская ветка: {parent_branch}
- Точка ответвления (run): {from_run}
- Дата создания: {today}

## 2. Цель ветки
<Опиши, какую задачу решает именно эта ветка рассуждений и чем она отличается от других.>

## 3. Правила работы в ветке
- Не изменять файлы `result_raw.md`.
- Все смысловые изменения — только через новые промпты и новые runs.
- При смене подхода — создавать новую ветку, а не переписывать историю.

## 4. История шагов (кратко)
- <здесь по мере работы добавляй: A_001 — что сделали — статус>

## 5. Итоговый статус ветки
(заполняется по завершению)
- Статус: активная / завершена / тупиковая / заморожена
- Итоговый артефакт: <ссылка на финальный файл/директорию>
- Краткий вывод: <что дала эта ветка>

"""

PROMPT_MD_TEMPLATE = """# Промпт для шага {run_id} (ветка {branch_id})

## 1. Метаданные
- Проект: {project_name}
- Ветка: {branch_id}
- Шаг (run): {run_id}
- Дата/время: {today}

## 2. Цель шага

{description}

(1–3 предложения — что именно ты хочешь получить от ИИ на этом шаге.)

## 3. Краткий контекст (для себя)

- Что уже есть по проекту:
  - <например: черновик ТЗ, архитектура, список ролей>
- От какого результата отталкиваемся (run): <если есть, впиши ID шага>

## 4. Ограничения и формат ответа

- Язык: русский.
- Не правь прошлые ответы, а формируй новый вариант.
- Формат ответа:
  1. Краткое резюме (3–5 пунктов).
  2. Основная часть.
  3. Список открытых вопросов (если есть).

---

## 5. ТЕКСТ ПРОМПТА, КОТОРЫЙ ОТПРАВЛЯЕМ В ИИ

<сюда дословно вставь текст, который ты отправляешь в ИИ>

"""

CONTEXT_MD_TEMPLATE = """# Контекст для шага {run_id} (ветка {branch_id})

## 1. Описание

Кратко опиши, что это за данные (ТЗ, лог, код и т.п.) и откуда они взялись.

## 2. Вставленный текст/данные

```text
<сюда можно вставить длинный текст контекста, который ты даёшь ИИ>
````

## 3. Примечания

- На что ИИ должен обратить особое внимание: <...>
    

"""

RESULT_RAW_MD_TEMPLATE = """# Сырой ответ ИИ для шага {run_id} (ветка {branch_id})

Вставь сюда копией полный ответ ИИ БЕЗ изменений.  
Не редактируй этот файл, чтобы история оставалась чистой.

"""

EVALUATION_MD_TEMPLATE = """# Оценка шага {run_id} (ветка {branch_id})

## 1. Метаданные

- Проект: {project_name}
    
- Ветка: {branch_id}
    
- Шаг (run): {run_id}
    
- Дата/время оценки: {today}
    

## 2. Статус шага

- Статус: ✅ Успешно / ⚠️ Частично / ❌ Неуспешно
    
- Одной строкой: <краткое резюме результата>
    

## 3. Что получилось хорошо

- Пункт 1
    
- Пункт 2
    

## 4. Проблемы и ограничения

- Пункт 1
    
- Пункт 2
    

## 5. Выводы

<1–3 предложения, стоит ли продолжать эту ветку и почему.>

## 6. Следующие действия

-  Новый шаг в этой же ветке: <ID и краткое описание>
    
-  Создать новую ветку от этого шага: <ID ветки и причина>
    
-  Зафиксировать результат как финальный для подзадачи <...>
    
-  Признать шаг тупиковым и не развивать далее
    

"""

# ---------- Утилиты ----------

def now_str():  
return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def write_if_missing(path: Path, content: str, verbose=True):  
if path.exists():  
if verbose:  
print(f"[skip] {path} уже существует", file=sys.stderr)  
return False  
path.parent.mkdir(parents=True, exist_ok=True)  
path.write_text(content, encoding="utf-8")  
if verbose:  
print(f"[ok] создан файл {path}")  
return True

def safe_write(path: Path, content: str):  
"""Создаёт файл, если его нет. Если есть — ругается и ничего не трогает."""  
if path.exists():  
print(f"[error] файл уже существует и не будет перезаписан: {path}", file=sys.stderr)  
return False  
path.parent.mkdir(parents=True, exist_ok=True)  
path.write_text(content, encoding="utf-8")  
print(f"[ok] создан файл {path}")  
return True

def generate_run_id(branch_dir: Path, branch_id: str) -> str:  
"""  
Генерирует ID шага в формате A_001, A_002, ...  
Буква берётся из первого символа branch_id.  
"""  
prefix = (branch_id[0].upper() if branch_id else "X")  
runs_dir = branch_dir / "runs"  
max_num = 0  
if runs_dir.exists():  
for child in runs_dir.iterdir():  
if child.is_dir():  
m = re.match(rf"{re.escape(prefix)}_(\d+)$", child.name)  
if m:  
n = int(m.group(1))  
max_num = max(max_num, n)  
return f"{prefix}_{max_num + 1:03d}"

# ---------- Обработчики команд ----------

def handle_init_project(args):  
root = Path(args.root).resolve()  
project_name = args.project  
project_dir = root / "ai" / project_name

```
print(f"[info] Инициализация проекта в {project_dir}")
project_dir.mkdir(parents=True, exist_ok=True)

today = now_str()

# Базовые файлы проекта
write_if_missing(
    project_dir / "project.md",
    PROJECT_MD_TEMPLATE.format(project_name=project_name, today=today),
)
write_if_missing(
    project_dir / "plan.md",
    PLAN_MD_TEMPLATE.format(project_name=project_name),
)
write_if_missing(
    project_dir / "journal.md",
    JOURNAL_MD_TEMPLATE,
)

# Папка веток
branches_dir = project_dir / "branches"
branches_dir.mkdir(exist_ok=True)

# Основная ветка A_main (по умолчанию создаём)
if args.with_main_branch:
    branch_dir = branches_dir / "A_main"
    branch_dir.mkdir(exist_ok=True)
    branch_info = branch_dir / "branch-info.md"
    write_if_missing(
        branch_info,
        BRANCH_INFO_TEMPLATE.format(
            branch_id="A_main",
            parent_branch="нет (корневая ветка)",
            from_run="n/a",
            today=today,
        ),
    )
    runs_dir = branch_dir / "runs"
    runs_dir.mkdir(exist_ok=True)

print("[done] Проект проинициализирован.")
```

def handle_create_branch(args):  
root = Path(args.root).resolve()  
project_dir = root / "ai" / args.project  
if not project_dir.exists():  
print(f"[error] проект не найден: {project_dir}", file=sys.stderr)  
sys.exit(1)

```
branch_id = args.branch
branches_dir = project_dir / "branches"
branch_dir = branches_dir / branch_id
branch_dir.mkdir(parents=True, exist_ok=True)

today = now_str()
parent = args.parent or "нет (корневая ветка)"
from_run = args.from_run or "n/a"

branch_info_path = branch_dir / "branch-info.md"
write_if_missing(
    branch_info_path,
    BRANCH_INFO_TEMPLATE.format(
        branch_id=branch_id,
        parent_branch=parent,
        from_run=from_run,
        today=today,
    ),
)

runs_dir = branch_dir / "runs"
runs_dir.mkdir(exist_ok=True)

print(f"[done] Ветка {branch_id} создана в проекте {args.project}.")
```

def handle_create_run(args):  
root = Path(args.root).resolve()  
project_dir = root / "ai" / args.project  
if not project_dir.exists():  
print(f"[error] проект не найден: {project_dir}", file=sys.stderr)  
sys.exit(1)

```
branches_dir = project_dir / "branches"
branch_dir = branches_dir / args.branch
if not branch_dir.exists():
    print(f"[error] ветка не найдена: {branch_dir}", file=sys.stderr)
    print("Сначала создай ветку командой create-branch.", file=sys.stderr)
    sys.exit(1)

# Определяем ID шага
if args.run_id:
    run_id = args.run_id
else:
    run_id = generate_run_id(branch_dir, args.branch)

run_dir = branch_dir / "runs" / run_id
if run_dir.exists():
    print(f"[error] каталог шага уже существует: {run_dir}", file=sys.stderr)
    sys.exit(1)
run_dir.mkdir(parents=True, exist_ok=False)

today = now_str()
description = args.description or "<Опиши, что хочешь получить от ИИ на этом шаге.>"

# Файлы шага
project_name = args.project

safe_write(
    run_dir / "prompt.md",
    PROMPT_MD_TEMPLATE.format(
        project_name=project_name,
        branch_id=args.branch,
        run_id=run_id,
        today=today,
        description=description,
    ),
)

safe_write(
    run_dir / "context.md",
    CONTEXT_MD_TEMPLATE.format(
        branch_id=args.branch,
        run_id=run_id,
    ),
)

safe_write(
    run_dir / "result_raw.md",
    RESULT_RAW_MD_TEMPLATE.format(
        branch_id=args.branch,
        run_id=run_id,
    ),
)

safe_write(
    run_dir / "evaluation.md",
    EVALUATION_MD_TEMPLATE.format(
        project_name=project_name,
        branch_id=args.branch,
        run_id=run_id,
        today=today,
    ),
)

print(f"[done] Создан шаг {run_id} в ветке {args.branch} проекта {args.project}.")
```

# ---------- CLI ----------

def build_parser():  
parser = argparse.ArgumentParser(  
prog="ai_flow.py",  
description="Утилита для создания структуры проектов с ИИ (ветки и шаги).",  
)  
parser.add_argument(  
"--root",  
default=".",  
help="Корневая директория репозитория/проекта (по умолчанию текущая).",  
)

```
subparsers = parser.add_subparsers(
    title="команды",
    dest="command",
    description="Доступные операции",
)

# init-project
p_init = subparsers.add_parser(
    "init-project",
    help="Инициализировать новый проект в каталоге ai/<project>.",
    description="Создаёт структуру проекта: project.md, plan.md, journal.md, "
                "директорию branches и основную ветку A_main.",
)
p_init.add_argument(
    "--project",
    required=True,
    help="Идентификатор проекта (например, 2025-12-01_my-project).",
)
p_init.add_argument(
    "--with-main-branch",
    action="store_true",
    default=True,
    help="Создать основную ветку A_main (по умолчанию включено).",
)
p_init.set_defaults(func=handle_init_project)

# create-branch
p_branch = subparsers.add_parser(
    "create-branch",
    help="Создать ветку рассуждений в проекте.",
    description="Создаёт ветку в ai/<project>/branches/<branch>/ "
                "с файлом branch-info.md и папкой runs.",
)
p_branch.add_argument(
    "--project",
    required=True,
    help="Идентификатор проекта (как в init-project).",
)
p_branch.add_argument(
    "--branch",
    required=True,
    help="Идентификатор ветки (например, A_main, B_alt-from-A_002).",
)
p_branch.add_argument(
    "--parent",
    help="Родительская ветка (опционально).",
)
p_branch.add_argument(
    "--from-run",
    help="ID шага (run), от которого ответвляется ветка (опционально).",
)
p_branch.set_defaults(func=handle_create_branch)

# create-run
p_run = subparsers.add_parser(
    "create-run",
    help="Создать шаг (run) в указанной ветке.",
    description="Создаёт каталог шага в branches/<branch>/runs/<run_id>/ "
                "и наполняет его шаблонными файлами prompt.md, context.md, "
                "result_raw.md, evaluation.md.",
)
p_run.add_argument(
    "--project",
    required=True,
    help="Идентификатор проекта.",
)
p_run.add_argument(
    "--branch",
    required=True,
    help="Идентификатор ветки (например, A_main).",
)
p_run.add_argument(
    "--run-id",
    help="ID шага (например, A_001). Если не задан, генерируется автоматически.",
)
p_run.add_argument(
    "--description",
    help="Краткое описание цели шага (попадёт в шаблон prompt.md).",
)
p_run.set_defaults(func=handle_create_run)

return parser
```

def main():  
parser = build_parser()  
args = parser.parse_args()

```
if not getattr(args, "command", None):
    parser.print_help()
    sys.exit(1)

args.func(args)
```

if **name** == "**main**":  
main()

````

---

### Как пользоваться

Сохрани скрипт, например, как `ai_flow.py` в корень репозитория.

Примеры:

```bash
# Общая помощь
python ai_flow.py --help

# Создать новый проект
python ai_flow.py init-project --project 2025-12-01_my-project

# Создать новую ветку рассуждений
python ai_flow.py create-branch \
  --project 2025-12-01_my-project \
  --branch B_alt-from-A_002 \
  --parent A_main \
  --from-run A_002

# Создать новый шаг (run) в ветке (ID шага сгенерируется автоматически: A_001, A_002, ...)
python ai_flow.py create-run \
  --project 2025-12-01_my-project \
  --branch A_main \
  --description "Собрать первичное ТЗ"
````

Если хочешь, могу в следующем шаге подогнать структуру под твой конкретный репозиторий (корни, имена проектов и т.д.), но сам скрипт уже самодостаточный и готов к использованию.