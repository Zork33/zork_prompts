# ТЗ: декомпозиция монолита Goldex и перенос на Node.js/TypeScript/TypeORM

## 1. Контекст и охват
Монолит (Go + GORM) реализует процессы бота: авторизация/сессии, оценка лома, выкуп, выплаты, магазин, чеки, прайс-гриды и файловое хранилище. Основные сущности и связи задокументированы в ER-справочнике, охватывающем ботов, сессии, оценки, сделки выкупа, платежи SBP/PNE и чеки магазина/выкупа.【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L1-L116】【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L165-L219】 Цель — описать сервисы, данные и бизнес-логику для эквивалентной реализации на Node.js/TypeScript/TypeORM с молекулярной (Moleculer) внутренней шиной и идемпотентными HTTP-контрактами для внешнего UI.

## 2. Целевое разбиение на микросервисы
| Сервис | Зона ответственности | Хранилище (TypeORM) | Внешние HTTP (идемпотент) | Внутренние вызовы (Moleculer actions) |
| --- | --- | --- | --- | --- |
| **auth-session** | Создание/финализация сессий бота, проверка телефона/SMS, привязка клиента | `bot_sessions`, `bot_clients`, `bot_staff` | POST /session (создание), PUT /session/{id}/phone, PUT /session/{id}/authorize, DELETE /session/{id} | `session.created`, `session.authorized` |
| **evaluation** | Прием спектра/веса, расчёт статусов, ревью, фото, стоимость | `bot_evaluations`, `bot_evaluation_cost`, `bot_evaluation_reviews`, `bot_photos` | PUT /evaluation/{id}, PUT /evaluation/{id}/finalize, GET /evaluation/{id} | `evaluation.finalized`, `evaluation.accepted` |
| **buyout-deal** | Создание и подтверждение сделки, генерация accept_code, связь с чеком | `bot_buyout_deals`, `bot_gridstore_buyout` | PUT /deal/{uid}, PUT /deal/{uid}/accept, GET /deal/{uid} | `deal.accepted`, запросы к `payout`, `receipt` |
| **payout** | Выплаты SBP/PNE, чек статусов, хранение реквизитов | `payout_sbp_payouts`, `payout_pne_payouts`, `payout_pne_bot_pos` | PUT /payout/{uid}, GET /payout/{uid} | Moleculer actions `payout.sbp.start`, `payout.pne.start`, `payout.status` |
| **receipt** | Генерация и загрузка чеков выкупа/магазина | `receipt_buyout_receipts`, `receipt_fd_checks`, `bot_buyout_bots` | PUT /receipt/buyout/{deal_uid}, PUT /receipt/shop/{purchase_uid}, GET /receipt/{id} | `receipt.printed`, обращение к файловому хранилищу |
| **shop** | Витрина, продажи, выдача из ячейки, платежные статусы | `bot_shop_products`, `bot_shop_product_images`, `bot_gridstore_shop`, `bot_bot_product_items`, `bot_shop_purchases`, `bot_dispenser_history` | GET /shop/products, PUT /shop/purchase/{uid}, PUT /shop/purchase/{uid}/status | `shop.purchase.created`, `receipt.shop.request` |
| **inventory** | Партии/экземпляры товара и buyout-слоты | `bot_product_stagings`, `bot_product_items`, `bot_gridstore_shop`, `bot_gridstore_buyout` | Только чтение для UI: GET /inventory/items | `inventory.reserve`, `inventory.release` |
| **pricing** | Прайс-гриды и коэффициенты | `bot_price_grids` | GET /price/{grid_id}, PUT /price/{grid_id} | `price.updated` |
| **files** | Файловое хранилище фото/подписей | файловая система + ссылки в `bot_photos`, `receipt_buyout_receipts`, `bot_staff` | PUT /files, GET /files/{id} | `files.persisted` |
| **promo** | Промо-валидация и гашение | таблица промо (внешний сервис) | POST /promo/validate (idempotent токен), POST /promo/redeem | `promo.redeemed` |
| **sms** | Отправка/логика счетчиков SMS | нет (использует очередь/провайдера) | POST /sms/send (идемпотент по message_id) | `sms.sent`, `sms.failed` |
| **gateway-bff** | Facade для UI, роутинг по сервисам, idempotency-key middleware | нет | Все UI эндпоинты | вызывает Moleculer actions | 

## 3. Схема данных (TypeORM)
Ниже обязательные поля и связи (PK/unique/FK) для ключевых сущностей. Типы адаптированы под TypeORM (`PrimaryGeneratedColumn`, `Column`, `ManyToOne`, `OneToMany`).

### bot_sessions
- `id` PK, `botId` FK -> `bot_bots`, `orgId` FK -> `bot_orgs`.
- `phoneNumber` (unique in bot_clients), `authorizationMethod`, `authorizedClientId` FK -> `bot_clients`.
- Флаги `authorized`, `phoneVerified`, счетчик SMS `smsCounter`, audit (`createdAt`, `updatedAt`, `finalized`, `finalizedAt`).【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L116-L139】 Логика финализации и авторизации привязана к сессии.【F:tmobile-gr-backend/bot/api/handler/sessionservice/begin.go†L15-L58】

### bot_clients
- PK `id`, `phoneNumber` (unique), `fullName`, паспортные поля, гражданство, `identified` bool.【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L116-L139】 Используются при выдаче чеков и выплатах.

### bot_evaluations
- PK `id`, FK `botId`, `sessionId`, `priceGridId`.
- Спектр и масса: `alloy`, `spectralContent`, `spectrumDetails`, `weight`, `densityScore`, `warnings` (CSV).【F:tmobile-gr-backend/bot/db/model/evaluation.go†L14-L52】
- Классификация: `jewelType`, `finenessId`, решение `autoDecision`, статус `status`, финализация `finalized`, `finalizedAt`, `rejectionReason`.
- Методы домена: `AcceptAutomatically`, `IsAccepted`, `Finalize` (перенести как сервисные функции).【F:tmobile-gr-backend/bot/db/model/evaluation.go†L54-L90】

### bot_evaluation_cost / review / photos
- `evaluation_cost`: FK `evalId`, поля `basePrice`, `price`, `cost`, `promo*`, `currency` (decimal).【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L139-L164】
- `evaluation_reviews`: PK/FK `evalId`, override проб/цен, `status`, `reviewerUserId`.【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L139-L164】
- `photos`: FK `evaluationId`, `path`, `photoType`, `coreFileId`, ссылка на `botId`.【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L139-L164】

### bot_buyout_deals
- PK `id`, `dealUid` unique, FK `evalId`, `sessionId`, `botId`, `orgId`, `clientId`.
- Платежные поля: `provider`, `paymentUid`, `currency`, `amount`, `status/statusDesc`, `acceptCode`, `accepted` bool, `smsCounter`, `docLink`, `testOperation`.【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L164-L188】 Логика accept_code и связка с фискальными чеками/выплатами.

### payout_* (sbp/pne)
- Общие: PK auto, FK `botId`, `sessionId`, `clientId`, `terminalId`, `evalId` (для SBP), суммы `amount`, `currency`, статусы `status/statusDesc`, идентификаторы `paymentUid`, `payoutUid`, `operationId`/`trxId`. Специфичные реквизиты: SBP (`bic`, `recipientAccount/name`), PNE (`ip`, `endpoint`, `maskedPan`, `pneMethod`).【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L188-L219】 

### receipt_buyout_receipts / receipt_fd_checks
- Buyout: FK `botId`, `evalId`, `clientId`, `sessionId`, поля payload/json, `status`, ссылки на файлы подписей `clientSigFileId`, `merchantSigFileId`, `uploadId`, `link` для выдачи чека.【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L116-L139】
- Shop: FK `sessionId`, `clientId`, `entityId` (purchase), реквизиты робота (ИНН, адрес), `amount`, `status/statusDesc`, `type/typeDesc`.【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L219-L256】

### bot_shop_products / purchases
- Products: PK `id`, `orgId`, `name`, `price`, `desc`, `images` (OneToMany).【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L139-L164】
- Gridstore slots: `bot_gridstore_shop` (bot+slot+product+count), dispenser history (item ids, session, deal).【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L45-L92】
- Purchases: PK `id`, `dealUid`, `paymentUid`, FK `botId`, `orgId`, `sessionId`, `productId`, `itemId`, суммы `amount/baseAmount`, `currency`, статусы `status/statusDesc`, `provider`, `promo*`, `testOperation`.【F:tmobile-gr-backend/bot/db/model/shop_purchase.go†L11-L55】

### bot_price_grids
- PK `id`, коэффициенты buyout/shop, валюты, пробелы (используются в расчётах стоимости).【F:tm-docs/goldex-docs/monolith/plan/data/join-data.md†L45-L92】

## 4. API и бизнес-логика (идемпотентные HTTP для UI)
Идемпотентность достигается через заголовок `Idempotency-Key` + уникальные `deal_uid`/`payment_uid`. Внутренне каждое действие проверяет существование записи и статусы, повторно возвращая тот же результат.

### 4.1 auth-session (пример логики на Python-псевдокоде)
```python
# POST /session
if req.auth_method != 'phone': return bad_request
sess = Session(bot_id=bot.id, finalized=False)
db.save(sess)
emit('session.created', sess.id)
return {"sessionId": str(sess.id)}

# PUT /session/{id}/phone
sess = load_session(id)
if sess.finalized: return conflict
if req.phone != sess.phone_number:
    update phone, reset sms_counter
code = gen_code(); send_sms(code)
sess.phone_verified = False; sess.sms_counter += 1; db.save(sess)
return 202

# PUT /session/{id}/authorize
sess = load_session(id)
if verify_code(req.code, sess):
    client = upsert_client(phone=req.phone, payload=req.passport)
    sess.authorized = True; sess.authorized_client_id = client.id
    db.save(sess)
    emit('session.authorized', sess.id)
    return 200
return forbidden
```

### 4.2 evaluation
```python
# PUT /evaluation/{id}
eval = upsert_by_goldex_eval_id(req.goldexEvalId)
assert_session(eval.session_id)
update spectrum/weight/status
if eval.accept_automatically(min_conf):
    finalize(eval, decision='accepted')
return eval

# PUT /evaluation/{id}/finalize
if eval.finalized: return current_state
apply_review_or_decision(req.decision, req.rejection_reason)
set finalized_at=now
emit('evaluation.finalized', eval.id)
```

### 4.3 buyout-deal
```python
# PUT /deal/{uid}
eval = find_eval(req.eval_id, bot_id)
if not eval.is_finalized(): return bad_request
buyout = get_or_create(deal_uid=uid)
buyout.amount = req.amount; buyout.currency = req.currency
buyout.accept_code = buyout.accept_code or gen_sms_code()
save(buyout); send_sms(buyout.accept_code)
return {"acceptCode": mask_code()}

# PUT /deal/{uid}/accept
if buyout.accepted: return ok
if req.code != buyout.accept_code: return forbidden
buyout.accepted=True; save(buyout)
emit('deal.accepted', buyout.id)
```

### 4.4 payout
```python
# PUT /payout/{uid}
p = get_or_create(payment_uid=uid)
if p.status in ('success','pending'): return p
route = 'sbp' if req.method=='sbp' else 'pne'
p.payload = req.bank_details
call_gateway_provider(route, req)
p.status='pending'; schedule_check(p)
return p

# GET /payout/{uid}
refresh_status_from_provider(p)
return p
```

### 4.5 receipt
```python
# PUT /receipt/buyout/{deal_uid}
deal = require_accepted_deal(deal_uid)
rcpt = get_or_create(eval_id=deal.eval_id)
if rcpt.status=='printed': return rcpt
payload = build_receipt_payload(deal, client, bot)
file_id = files.save_pdf(payload)
rcpt.status='printed'; rcpt.link=file_id
emit('receipt.printed', rcpt.id)
return rcpt
```

### 4.6 shop
```python
# PUT /shop/purchase/{uid}
purch = get_or_create(deal_uid=uid)
reserve_item(slot=req.slot, item_id=req.item_id)
purch.amount=req.amount; purch.status='pending'
initiate_payment(purch)
return purch

# PUT /shop/purchase/{uid}/status
purch = load_by_uid(uid)
update_status(req.status, req.payment_uid)
if status=='paid': emit('receipt.shop.request', purch.id)
```

## 5. Внутренние связи (Moleculer)
- События: `session.created`, `session.authorized`, `evaluation.finalized`, `deal.accepted`, `payout.updated`, `receipt.printed`, `shop.purchase.created`.
- Actions: `promo.validate/redeem`, `files.save`, `pricing.get`, `inventory.reserve/release`, `payout.sbp.start`, `payout.pne.start`, `receipt.generate`, `dash.notify` (аналог NATS вызова `dash.SessionStarted`).【F:tmobile-gr-backend/bot/api/handler/sessionservice/begin.go†L32-L49】
- Bus-bridge: Moleculer transporter=NATS, сериализация protobuf для совместимости с текущим NRPC-клиентом (см. миграционные риски).【F:tm-docs/goldex-docs/monolith/migration/MIGRATION_REVIEW.md†L1-L20】 

## 6. Идемпотентность и авторизация
- Использовать middleware Gateway: проверка JWT бота (по аналогии с `NewBotAuther`) и заголовка `Idempotency-Key`; при повторе возвращать сохранённый ответ.
- Все мутирующие операции — PUT/POST/DELETE с детерминированными ключами (`sessionId`, `deal_uid`, `payment_uid`).
- Чтения — GET, всегда безопасны.

## 7. Идеи по улучшению структуры
1. **Полная схематизация БД**: покрыть TypeORM-миграциями весь дамп `dump-tm-dev.sql`, включая payout, receipt, fileserver, чтобы убрать риск несовместимостей при cutover.【F:tm-docs/goldex-docs/monolith/migration/MIGRATION_REVIEW.md†L1-L15】
2. **Adapter NRPC ⇄ Moleculer**: описать и реализовать слой, который транслирует существующие protobuf-пакеты (dash/payout) в actions для плавной миграции клиентов Go.【F:tm-docs/goldex-docs/monolith/migration/MIGRATION_REVIEW.md†L1-L20】
3. **Контрактное тестирование Gateway**: для каждого маршрута OpenAPI + contract tests, чтобы переключение с Go на Node было пошаговым и обратимым.
4. **Observability и лимиты**: ввести correlation-id, quota на SMS/выплаты, алерты на зависания статусов payout/receipt.
5. **Переиспользование артефактов robot**: импортировать ent-схемы/тесты из `goldexrobot/business/*` для сравнения схем, dual-read на этапе миграции.【F:tm-docs/goldex-docs/monolith/migration/MIGRATION_REVIEW.md†L17-L32】

## 8. Ожидаемые артефакты Node.js
- **Entities**: TypeORM модели для всех таблиц выше + миграции.
- **Services**: Moleculer services per домен с actions, subscriptions на события и HTTP-gateway маршруты.
- **BFF**: Quasar/Vue фронт соединён с Gateway; все публичные вызовы идемпотентны.
- **CI/CD**: линтеры (ESLint), тесты (Jest), contract tests, миграции.

