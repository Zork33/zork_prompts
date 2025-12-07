# Промпт для генератора e2e/интеграционных тестов business-v1 (Node.js/TypeScript/Jest)

Цель: сгенерировать набор детальных тестов для сервиса **business-v1** (gRPC Bot API) с нуля на Node.js/TypeScript с Jest, используя пустую БД (структура MySQL из `tm-dev`) и наполнение фикстурами. Тесты должны проверять основные бизнес-потоки сессии → оценка → скупка → выплаты/статусы, а также edge-cases и валидаторы.

## 1. Контекст системы
- Основные модули: Session/Eval/Buyout/Status use-case слои, работающие поверх GORM-репозитория, Core API, S3 загрузчика фото, платежей Paynet PAN/SBP, SMS/печати/фискализации и публикатора событий NATS. gRPC сервер оборачивает auth-middleware с обязательными метаданными (`core_bot_id`, `core_project_id`, `core_bot_serial`, `idempotency_key`).【F:tm-docs/goldex-docs/current/business-v1.md†L2-L49】
- Модель данных: `Session (bot_sessions)`, `Client (bot_clients)`, `Evaluation (bot_evaluations)`, `EvaluationCost (bot_evaluation_cost)`, `BuyoutDeal (bot_buyout_deals)`, `GridstoreBuyout/GridstoreShop` с уникальными индексами по ячейкам/штампам и связями 1:1/1:many между сущностями.【F:tm-docs/goldex-docs/current/business-v1.md†L71-L99】
- Ключевые алгоритмы:
  - Расчёт цены `PriceGridCost` с валидацией веса/чистоты, подбором множителей по сплаву и округлением цены/стоимости.【F:tm-docs/goldex-docs/current/business-v1.md†L136-L142】
  - `BuyoutUseCase.Begin`: проверка финализированной оценки, резервирование ячейки, генерация квитанции/кода, создание `BuyoutDeal`, отправка SMS.【F:tm-docs/goldex-docs/current/business-v1.md†L144-L157】
  - `ResendSMS/Confirm`: повторная отправка с ростом счётчика и проверкой кода без изменения сделки при INVALID_CODE.【F:tm-docs/goldex-docs/current/business-v1.md†L158-L160】
  - `PayoutPANPaynet` и `HandlePaymentCheck`: статусы Prepared→Pending→Confirmed/Failed, idempotency key из метаданных, блокировка ячейки, тайм-ауты TTL для Pending и перевод ячейки в `GSCellBoughtOut` при успешной выплате.【F:tm-docs/goldex-docs/current/business-v1.md†L162-L180】
  - `StatusUseCase.Features/StorageSync`: доступные фичи и синхронизация ячеек с фиксацией конфликтов, освобождением пропавших ячеек и запретом неизвестных доменов/дубликатов.【F:tm-docs/goldex-docs/current/business-v1.md†L182-L185】
- Родственный контур robot/v1: сервисы auth/session/buyout/dispenser/storage и др. используют типовую Kratos-архитектуру (server → service → biz/usecase → data/repo), TTLMap для SMS/лимитов, проверки роли `BuyoutAdmin`, агрегации buyout за 24 месяца — можно использовать как референс при проектировании тестовых double/mock-реализаций RPC/репозиториев.【F:tm-docs/goldex-docs/robot/business-back.md†L2-L176】

## 2. Требования к тестовой среде
- **Стек**: Node.js 18+, TypeScript, Jest (ts-jest/ESM поддержка), supertest для HTTP-gRPC proxy, testcontainers/mysql для подъёма временной MySQL (инициализация из дампа схемы `db_backup/dump-tm-dev.sql`), **TypeORM** (DataSource + репозитории) для удобной и типобезопасной работы с таблицами tm-dev и проверки побочных эффектов.
- **БД**: стартовая БД пустая, но со схемой tm-dev. Вставить минимальные фикстуры через SQL seed или ORM миграции. Опирайтесь на структуру таблиц:
  - `bot_sessions`: PK `id`, поля `bot_id`, `finalized`, `phone_number`, `confirmation_code`, `authorized`, `authorized_client_id`, `sms_counter`, `phone_verified`, индексы/foreign key на `bot_clients`.【F:db_backup/dump-tm-dev.sql†L738-L759】
  - `bot_evaluations`: PK `id`, ссылки на `org_id`, `bot_id`, `session_id`, `status`, измерения, `core_eval_id`, `rejection_reason`, флаги finalization; FK на `bot_sessions`.【F:db_backup/dump-tm-dev.sql†L401-L429】
  - `bot_gridstore_buyout`: PK `id`, уникальный `bot_id+cell+release_stamp`, FK `eval_id` → `bot_evaluations`. Используется при резервировании/покупке ячеек.【F:db_backup/dump-tm-dev.sql†L445-L461】
  - `bot_price_grids` и `bot_metal_prices`: коэффициенты/цены для расчёта `PriceGridCost`. Используйте актуальные поля `gold_*`, `silver_*`, `metal/time/amount`.【F:db_backup/dump-tm-dev.sql†L636-L657】【F:db_backup/dump-tm-dev.sql†L512-L520】
  - `bot_orgs` для реквизитов организации (квитанции/платежи), `bot_payments` для отражения статусов выплат, `bot_photos` для ссылок на фото оценок (Core→S3).【F:db_backup/dump-tm-dev.sql†L533-L594】【F:db_backup/dump-tm-dev.sql†L609-L623】

### 2.1 Контейнеризация БД/сервисов
- **MySQL контейнер**: использовать testcontainers/mysql для поднятия инстанса, затем накатывать `db_backup/dump-tm-dev.sql` (структура + опционально базовые словари). Хранить SQL в каталоге `tests/fixtures/sql` и прогонять через `mysql` CLI или TypeORM QueryRunner перед тестами.
- **Подъём сервисов business-v1 и business-v2**: поднимать оба бэкенда в контейнерах/локально (например, docker-compose или testcontainers/generic-container) с отдельными переменными окружения для подключения к общей MySQL или двум разным экземплярам (рекомендация: раздельные БД в одном MySQL контейнере, схемы `business_v1_test`, `business_v2_test`).
- **Изоляция**: каждый тестовый suite может использовать отдельную базу/схему через настройку окружения контейнеров, либо последовательный `TRUNCATE` при параллельном запуске с Jest worker’ами.

### 2.2 Параллельное тестирование v1 vs v2
- Поднимайте **оба** сервиса (business-v1 и business-v2) одновременно и направляйте идентичные запросы в рамках одного теста на оба RPC/HTTP endpoints.
- Проверяйте **эквивалентность ответов** (payload, коды ошибок/статусы) и, по возможности, сравнивайте **тайминги**: фиксируйте `Date.now()`/`performance.now()` до/после вызова, сохраняйте метрики в отчёт (например, Jest custom reporter) и добавляйте проверку допустимого расхождения (например, `|t_v1 - t_v2| < 50-100 мс`, настраиваемый допуск).
- Для различий между версиями: явно документируйте расхождения в snapshot/золотых образцах и помечайте как ожидаемые или баги.

## 3. Наполнение данными (fixtures)
Примерный seed (SQL/Prisma миграции) для каждого кейса:
- **Боты/орг**: 1 запись в `bot_orgs` (org_id=100), 1 бот (`bot_bots` если есть схема) с включёнными фичами buyout/shop, привязка к price_grid, buyout_bot/receipt_counter по умолчанию. Разрешить тестовый режим (test_operation=true) для отдельного бота.
- **Клиент/сессия**: вставить `bot_clients` с msisdn, паспортом; `bot_sessions` с `finalized=false`, `sms_counter=0`, `phone_verified=false`, `authorized=false` и `confirmation_code` (для позитивных/негативных кодов). Подготовить вторую финализированную сессию (старше 1ч) для edge-case TTL.
- **Оценки**: две `bot_evaluations`: (а) Finished+Finalized с допустимыми измерениями (Au, weight>0) и `core_eval_id`; (б) Rejected/Cancelled для негативных сценариев. Для первой — `bot_evaluation_cost` с ценой>0 и промо-флагами; для второй — cost=0.
- **Gridstore**: `bot_gridstore_buyout` с `status=PreAlloc`/`Inactive` для проверки конфликтов и освобождения ячеек; `bot_gridstore_shop` набор ячеек с дубликатами для негативного `StorageSync`.
- **Price grid/metal prices**: заполнить `bot_price_grids` (gold/silver multipliers) и `bot_metal_prices` (metal=gold 999.9, currency=RUB) на ближайшее время для расчёта `PriceGridCost`.
- **BuyoutDeal**: одна Prepared сделка (AcceptCode=0000, TestOperation=true) связана с финализированной оценкой; одна Pending с реальным кодом и PaymentUID для проверки `HandlePaymentCheck`; одна Failed для повторной выплаты.
- **Payments/receipts**: при необходимости — минимальные строки в `bot_payments` для статусов payout и соответствующие поля `provider/method/status`.

## 4. Области покрытия тестов (предложить генератору)
1. **Аутентификация метаданных**: отсутствие/невалидные `core_bot_id`/`idempotency_key` → gRPC PermissionDenied/FailedPrecondition; позитивный путь с корректными метаданными.
2. **Session lifecycle**:
   - Создание сессии и старт оценки (SessionStarted event mock); TTL >1h → автфинализация.
   - Верификация телефона: успешное подтверждение кода, неверный код не меняет статус (`sms_counter` растёт в ResendSMS).
3. **Evaluation**:
   - `Begin` создаёт Started, `Updated` тянет финальные данные Core и ставит Finalized+Finished, размещает задачу на фото (проверка записи в `bot_photos`).
   - Негатив: повторное `Begin` на финализированную оценку → FailedPrecondition; `Photo` ставит S3-очередь.
4. **Price calculation** (`PriceGridCost`):
   - Позитив: Au проба 585/999, корректное округление цены/стоимости по multipliers и `metal price`.
   - Edge: вес ≤0, purity вне 1..100, неподдерживаемый alloy → ошибки.
5. **Buyout Begin/Confirm/ResendSMS**:
   - Успешный Begin: блокировка ячейки, создание Prepared сделки, генерация AcceptCode (0000 в тесте), SMS отправлена (mock call), квитанция/DocLink сохранён в нетестовом режиме.
   - ResendSMS увеличивает `SMSCounter` и меняет ссылку (#n).
   - Confirm: неверный AcceptCode → INVALID_CODE без изменений; верный → Accepted=true.
6. **Payout Paynet/SBP**:
   - Инициация выплаты: Prepared+Accepted → Pending с `payment_uid`, сохранение provider, постановка в очередь; Failed ответ провайдера → статус Failed.
   - Повтор с тем же idempotency_key не создаёт дубликатов (проверка статуса/PaymentUID).
   - `HandlePaymentCheck`: Pending→Confirmed меняет Gridstore статус на `GSCellBoughtOut`; Pending с истёкшим TTL → Failed.
7. **Status/StorageSync**:
   - `Features`: возвращает доступные фичи/платёжки в зависимости от провайдеров (mock `IsAvailable` true/false).
   - `StorageSync` OK: обновляет/создаёт ячейки, освобождает пропавшие (release_stamp меняется); CONFLICT с дубликатами/неизвестным доменом.
8. **События NATS**: проверка публикации `BotOnline`, `EvaluationDataUpdated`, `CustomerReviewRequired` с правильными payload (использовать mock event bus). Ретраи/логирование ошибок не должны срывать основной RPC.
9. **Error handling & transactions**: rollback при ошибках БД/провайдеров, маппинг бизнес-предусловий в gRPC ошибки (`FailedPrecondition`, `PermissionDenied`, `NotFound`, `Internal`).

## 5. Структура тестов (предложение)
- `tests/setup.ts`: поднятие MySQL контейнера, применение схемы, прогон seed SQL, создание тестовых gRPC/HTTP клиентов с нужными метаданными.
- `tests/mocks`: фальш реализация Core API, S3 uploader, Paynet/SBP, SMS sender, printer/fiscal, NATS publisher (фиксировать вызовы/параметры).
  - Для SMS функциональности использовать мок/фальш-адаптер (например, in-memory counter + last message storage). Это исключает реальные отправки, позволяет проверять рост `sms_counter`, корректность AcceptCode/confirmation_code и тексты сообщений. При необходимости добавить spy на внешний SMS SDK, но сетевые вызовы запрещены.
- `tests/e2e/*.spec.ts`: набор describe-блоков по доменам (Session, Eval, Buyout, Status) с изолированными фикстурами и очисткой таблиц между кейсами транзакциями или `TRUNCATE`.
- Общие helper’ы: генерация idempotency_key, сборка metadata, функции `seedSession`, `seedEvaluation`, `seedPriceGrid`, `seedGridstore`, `seedBuyoutDeal` с использованием типизированных моделей.

## 6. Формат выдачи генератора
- Сгенерировать полный код тестов (TypeScript) и SQL seed для MySQL.
- В каждом тесте явно описывать ожидаемые изменения в БД (проверка таблиц через ORM/SQL после вызова RPC) и ответов gRPC/HTTP.
- Добавить комментарии с ссылками на соответствующие шаги бизнес-алгоритмов из спецификации (например, `// см. BuyoutUseCase.Begin шаги ...`).
- Включить пример запуска: `npm test` с предварительным `npm run db:seed` (скрипт накатывает дамп схемы и фикстуры).

## 7. Критерии готовности
- Покрыты все перечисленные happy/edge сценарии.
- Тесты изолированы, повторяемы на пустой БД tm-dev, все внешние зависимости замоканы или поднимаются тест-контейнерами.
- Явно проверяются транзакционные побочные эффекты (ячейки, статусы, SMS счётчики, события).
