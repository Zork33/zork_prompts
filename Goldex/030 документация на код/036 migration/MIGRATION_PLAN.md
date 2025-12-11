# План миграции T-Mobile Backend на Node.js + Moleculer

## Содержание

1. [Анализ текущей архитектуры](#1-анализ-текущей-архитектуры)
2. [Целевая архитектура](#2-целевая-архитектура)
3. [Стратегия миграции](#3-стратегия-миграции)
4. [Детальный план по сервисам](#4-детальный-план-по-сервисам)
5. [Общие компоненты](#5-общие-компоненты)
6. [План работ по этапам](#6-план-работ-по-этапам)
7. [Риски и митигация](#7-риски-и-митигация)

---

## 1. Анализ текущей архитектуры

### 1.1 Текущий стек

| Компонент | Технология |
|-----------|------------|
| Язык | Go 1.20 |
| Inter-service | NATS + NRPC (protobuf) |
| HTTP | Chi router |
| ORM | GORM |
| Auth | JWT |
| Notifications | Telegram, WebSocket |
| Payments | PaynetEasy, SBP (RSB, Tinkoff) |
| Fiscal | OrangeData |

### 1.2 Текущие приложения

```
┌─────────────────────────────────────────────────────────────┐
│                        MONOLITH                             │
├─────────────┬─────────────┬─────────────┬─────────────────┬─┤
│     Bot     │    Dash     │   Payout    │    Receipt      │ │
│  (31 API)   │  (WebUI)    │ (Payments)  │   (PDF/Fiscal)  │ │
├─────────────┼─────────────┼─────────────┼─────────────────┤ │
│   Price     │ Fileserver  │             │                 │ │
│  (Prices)   │  (Files)    │             │                 │ │
└─────────────┴─────────────┴─────────────┴─────────────────┴─┘
                            │
                      ┌─────┴─────┐
                      │   NATS    │
                      │  (NRPC)   │
                      └───────────┘
```

### 1.3 Выявленные домены

| Домен | Ответственность | Текущее расположение |
|-------|-----------------|---------------------|
| **Identity** | Сессии, клиенты, верификация | bot/api/handler/sessionservice |
| **Evaluation** | Оценка металлов, Goldex интеграция | bot/api/handler/evalservice |
| **Buyout** | Скупка, сделки, подтверждение | bot/api/handler/buyoutservice |
| **Shop** | Магазин, товары, покупки | bot/api/handler/shopservice |
| **Payment** | PaynetEasy, SBP обработка | payout/* |
| **Pricing** | Цены на металлы | price/* |
| **Documents** | PDF чеки, фискализация | receipt/* |
| **Storage** | Файлы, фото | fileserver/* |
| **Notifications** | Telegram, WebSocket | dash/* |
| **Admin** | Дашборд, мониторинг | dash/* |

---

## 2. Целевая архитектура

### 2.1 Целевой стек

| Компонент | Технология |
|-----------|------------|
| Runtime | Node.js 20 LTS |
| Framework | Moleculer 0.14+ |
| Transport | NATS (Moleculer native) |
| HTTP Gateway | Moleculer API Gateway |
| ORM | TypeORM |
| Validation | Zod / Fastest-validator |
| Auth | JWT (jsonwebtoken) |
| WebSocket | Socket.io / ws |
| Queue | Moleculer built-in / BullMQ |

### 2.2 Новая структура микросервисов

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY                                 │
│                    (moleculer-web + auth)                           │
└────────────────────────────┬────────────────────────────────────────┘
                             │ NATS
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────┴───────┐   ┌────────┴───────┐   ┌───────┴───────┐
│   IDENTITY    │   │   EVALUATION   │   │    BUYOUT     │
│   SERVICE     │   │    SERVICE     │   │   SERVICE     │
│  - sessions   │   │  - eval mgmt   │   │  - deals      │
│  - clients    │   │  - goldex int  │   │  - confirm    │
│  - phone auth │   │  - cost calc   │   │  - status     │
└───────────────┘   └────────────────┘   └───────────────┘
        │                    │                    │
        ├────────────────────┼────────────────────┤
        │                    │                    │
┌───────┴───────┐   ┌────────┴───────┐   ┌───────┴───────┐
│     SHOP      │   │    PAYMENT     │   │    PRICING    │
│   SERVICE     │   │    SERVICE     │   │   SERVICE     │
│  - products   │   │  - paynet      │   │  - gold/silver│
│  - purchases  │   │  - sbp         │   │  - currency   │
│  - inventory  │   │  - status      │   │  - goldex     │
└───────────────┘   └────────────────┘   └───────────────┘
        │                    │                    │
        ├────────────────────┼────────────────────┤
        │                    │                    │
┌───────┴───────┐   ┌────────┴───────┐   ┌───────┴───────┐
│   DOCUMENT    │   │    STORAGE     │   │ NOTIFICATION  │
│   SERVICE     │   │    SERVICE     │   │   SERVICE     │
│  - pdf gen    │   │  - upload      │   │  - telegram   │
│  - orangedata │   │  - download    │   │  - websocket  │
│  - templates  │   │  - meta        │   │  - events     │
└───────────────┘   └────────────────┘   └───────────────┘
                             │
                    ┌────────┴───────┐
                    │     ADMIN      │
                    │    SERVICE     │
                    │  - dashboard   │
                    │  - monitoring  │
                    │  - operators   │
                    └────────────────┘
```

### 2.3 Маппинг сервисов Go → Node.js

| Go App | Go Handler | Node.js Service | Moleculer Actions |
|--------|------------|-----------------|-------------------|
| bot | sessionservice | identity | `identity.session.*`, `identity.client.*`, `identity.phone.*` |
| bot | evalservice | evaluation | `evaluation.begin`, `evaluation.finish`, `evaluation.cost` |
| bot | buyoutservice | buyout | `buyout.begin`, `buyout.confirm`, `buyout.payout.*`, `buyout.status` |
| bot | shopservice | shop | `shop.list`, `shop.prepare`, `shop.payment.*`, `shop.status` |
| payout | pneservice | payment | `payment.paynet.*` |
| payout | sbpservice | payment | `payment.sbp.*` |
| price | - | pricing | `pricing.gold`, `pricing.silver` |
| receipt | printservice | document | `document.receipt.*` |
| receipt | orangeservice | document | `document.fiscal.*` |
| fileserver | - | storage | `storage.upload`, `storage.download`, `storage.link` |
| dash | - | notification | `notification.telegram.*`, `notification.websocket.*` |
| dash | - | admin | `admin.dashboard.*`, `admin.users.*` |

---

## 3. Стратегия миграции

### 3.1 Подход: Strangler Fig Pattern

Постепенная замена компонентов монолита микросервисами без прерывания работы системы.

```
Этап 1: ┌─────────────────────────────────────────────────────┐
        │ Go Monolith (100%)                                  │
        └─────────────────────────────────────────────────────┘

Этап 2: ┌─────────────────────────────────┐ ┌─────────────────┐
        │ Go Monolith (80%)               │ │ Node.js (20%)   │
        │                                 │ │ pricing,storage │
        └─────────────────────────────────┘ └─────────────────┘

Этап 3: ┌───────────────────┐ ┌───────────────────────────────┐
        │ Go Monolith (40%) │ │ Node.js (60%)                 │
        │ bot, payout       │ │ pricing,storage,document,notif│
        └───────────────────┘ └───────────────────────────────┘

Этап 4: ┌─────────────────────────────────────────────────────┐
        │ Node.js Moleculer (100%)                            │
        └─────────────────────────────────────────────────────┘
```

### 3.2 Принципы миграции

1. **Независимость** - каждый сервис можно мигрировать отдельно
2. **Обратная совместимость** - API контракты сохраняются
3. **Feature flags** - переключение между Go и Node.js
4. **Dual-write** - параллельная запись для критичных данных
5. **Shadow testing** - сравнение результатов Go vs Node.js

### 3.3 Порядок миграции

```
1. pricing      (низкий риск, нет состояния)
      ↓
2. storage      (изолированный, простая логика)
      ↓
3. document     (PDF генерация, fiscal)
      ↓
4. notification (Telegram, WebSocket)
      ↓
5. evaluation   (Goldex интеграция)
      ↓
6. identity     (сессии, клиенты)
      ↓
7. shop         (покупки, товары)
      ↓
8. buyout       (основная бизнес-логика)
      ↓
9. payment      (критичный, последний)
      ↓
10. admin       (dashboard)
```

---

## 4. Детальный план по сервисам

### 4.1 Pricing Service

**Приоритет:** 1 (первый для миграции)
**Сложность:** Низкая
**Риск:** Минимальный

**Текущая реализация (Go):**
- `price/rpc/priceservice/` - NRPC сервис
- Интеграция с Goldex Core API
- Кэширование цен

**Новая структура (Node.js):**
```
services/pricing/
├── pricing.service.ts        # Moleculer service
├── actions/
│   ├── gold.action.ts        # pricing.gold
│   └── silver.action.ts      # pricing.silver
├── integrations/
│   └── goldex.client.ts      # Goldex API client
├── cache/
│   └── price.cache.ts        # Redis/memory cache
└── types/
    └── price.types.ts        # TypeScript types
```

**Moleculer Actions:**
```typescript
// pricing.service.ts
actions: {
  gold: {
    params: { currency: "string" },
    handler(ctx) { /* return gold prices */ }
  },
  silver: {
    params: { currency: "string" },
    handler(ctx) { /* return silver prices */ }
  }
}
```

**Задачи:**
- [ ] Создать базовую структуру Moleculer проекта
- [ ] Реализовать Goldex API клиент (axios/got)
- [ ] Реализовать кэширование (Moleculer cacher)
- [ ] Написать unit тесты
- [ ] Настроить CI/CD
- [ ] Провести нагрузочное тестирование

---

### 4.2 Storage Service

**Приоритет:** 2
**Сложность:** Низкая
**Риск:** Низкий

**Текущая реализация (Go):**
- `fileserver/` - HTTP сервер + NRPC
- Chunked upload/download
- MIME type support

**Новая структура (Node.js):**
```
services/storage/
├── storage.service.ts
├── actions/
│   ├── upload.action.ts      # storage.upload
│   ├── download.action.ts    # storage.download
│   └── link.action.ts        # storage.link
├── providers/
│   ├── local.provider.ts     # Local filesystem
│   └── gcs.provider.ts       # Google Cloud Storage (future)
├── middleware/
│   └── multer.middleware.ts  # File upload handling
└── types/
    └── storage.types.ts
```

**Задачи:**
- [ ] Реализовать chunked upload (multer/busboy)
- [ ] Реализовать streaming download
- [ ] Добавить поддержку MIME types
- [ ] Реализовать URL generation
- [ ] Написать интеграционные тесты

---

### 4.3 Document Service

**Приоритет:** 3
**Сложность:** Средняя
**Риск:** Средний (фискализация)

**Текущая реализация (Go):**
- `receipt/rpc/printservice/` - PDF генерация
- `receipt/rpc/orangeservice/` - OrangeData интеграция
- RSA подпись запросов

**Новая структура (Node.js):**
```
services/document/
├── document.service.ts
├── actions/
│   ├── receipt/
│   │   ├── print.action.ts       # document.receipt.print
│   │   └── template.action.ts    # document.receipt.template
│   └── fiscal/
│       ├── send.action.ts        # document.fiscal.send
│       └── status.action.ts      # document.fiscal.status
├── generators/
│   ├── pdf.generator.ts          # PDFKit/Puppeteer
│   └── templates/
│       └── buyout.template.ts
├── integrations/
│   └── orangedata.client.ts      # OrangeData API
├── crypto/
│   └── rsa.signer.ts             # RSA signing
└── queue/
    └── fiscal.queue.ts           # BullMQ for async
```

**Библиотеки:**
- PDF: `pdfkit` или `puppeteer`
- Crypto: `node:crypto` (RSA)
- Queue: `bullmq`

**Задачи:**
- [ ] Портировать PDF шаблоны
- [ ] Реализовать RSA подпись
- [ ] Интегрировать OrangeData API
- [ ] Реализовать очередь фискализации
- [ ] Тестирование с prod OrangeData (sandbox)

---

### 4.4 Notification Service

**Приоритет:** 4
**Сложность:** Средняя
**Риск:** Низкий

**Текущая реализация (Go):**
- `dash/` - Telegram bot + WebSocket
- NRPC события от других сервисов

**Новая структура (Node.js):**
```
services/notification/
├── notification.service.ts
├── actions/
│   ├── telegram/
│   │   ├── send.action.ts        # notification.telegram.send
│   │   └── notify.action.ts      # notification.telegram.notify
│   └── websocket/
│       ├── broadcast.action.ts   # notification.websocket.broadcast
│       └── room.action.ts        # notification.websocket.room
├── channels/
│   ├── telegram.channel.ts       # Telegraf
│   └── websocket.channel.ts      # Socket.io
├── templates/
│   └── messages.ts               # Message templates
└── events/
    └── handlers.ts               # Event subscriptions
```

**Библиотеки:**
- Telegram: `telegraf`
- WebSocket: `socket.io`

**Moleculer Events:**
```typescript
events: {
  "session.started": { handler: this.onSessionStarted },
  "eval.review": { handler: this.onEvalReview },
  "buyout.completed": { handler: this.onBuyoutCompleted },
  "shop.completed": { handler: this.onShopCompleted }
}
```

**Задачи:**
- [ ] Настроить Telegraf bot
- [ ] Реализовать WebSocket комнаты
- [ ] Подписаться на Moleculer events
- [ ] Портировать шаблоны сообщений
- [ ] Тестирование с Telegram API

---

### 4.5 Evaluation Service

**Приоритет:** 5
**Сложность:** Высокая
**Риск:** Средний

**Текущая реализация (Go):**
- `bot/api/handler/evalservice/` - HTTP handlers
- `bot/callback/` - Goldex callbacks
- `common/cost/` - расчет стоимости
- `common/fineness/` - расчеты сплавов

**Новая структура (Node.js):**
```
services/evaluation/
├── evaluation.service.ts
├── actions/
│   ├── begin.action.ts           # evaluation.begin
│   ├── finish.action.ts          # evaluation.finish
│   ├── abort.action.ts           # evaluation.abort
│   ├── cost.action.ts            # evaluation.cost
│   └── review.action.ts          # evaluation.review
├── callbacks/
│   └── goldex.callback.ts        # /callback/eval-photo
├── calculators/
│   ├── cost.calculator.ts        # Pricing logic
│   └── fineness.calculator.ts    # Alloy calculations
├── integrations/
│   └── goldex.client.ts          # Goldex API
├── entities/
│   ├── evaluation.entity.ts
│   └── photo.entity.ts
└── types/
    └── evaluation.types.ts
```

**Критичная логика для портирования:**
```typescript
// cost.calculator.ts - из common/cost/
export function estimate(
  weight: Decimal,
  alloy: Alloy,
  jewelType: JewelType,
  currency: Currency,
  pricer: Pricer
): Decimal { /* ... */ }

// fineness.calculator.ts - из common/fineness/
export function calculateFineness(
  spectrum: SpectrumData,
  alloy: Alloy
): Fineness { /* ... */ }
```

**Задачи:**
- [ ] Портировать cost calculator с тестами
- [ ] Портировать fineness calculator с тестами
- [ ] Реализовать Goldex callback сервер
- [ ] Интегрировать с pricing service
- [ ] Интегрировать со storage service
- [ ] Реализовать operator review flow

---

### 4.6 Identity Service

**Приоритет:** 6
**Сложность:** Средняя
**Риск:** Средний (персональные данные)

**Текущая реализация (Go):**
- `bot/api/handler/sessionservice/` - сессии
- `common/sms/` - SMS отправка
- `common/passchecker/` - проверка паспорта

**Новая структура (Node.js):**
```
services/identity/
├── identity.service.ts
├── actions/
│   ├── session/
│   │   ├── begin.action.ts       # identity.session.begin
│   │   ├── end.action.ts         # identity.session.end
│   │   └── authorize.action.ts   # identity.session.authorize
│   ├── client/
│   │   ├── create.action.ts      # identity.client.create
│   │   └── update.action.ts      # identity.client.update
│   └── phone/
│       ├── send.action.ts        # identity.phone.send
│       ├── verify.action.ts      # identity.phone.verify
│       └── resend.action.ts      # identity.phone.resend
├── integrations/
│   ├── smsc.client.ts            # SMSC provider
│   └── passchecker.client.ts     # Passport validation
├── entities/
│   ├── session.entity.ts
│   └── client.entity.ts
└── validators/
    └── passport.validator.ts
```

**Задачи:**
- [ ] Реализовать session management
- [ ] Портировать SMSC интеграцию
- [ ] Портировать passport checker
- [ ] Реализовать rate limiting (SMS)
- [ ] Обеспечить защиту персональных данных (encryption)

---

### 4.7 Shop Service

**Приоритет:** 7
**Сложность:** Средняя
**Риск:** Средний

**Текущая реализация (Go):**
- `bot/api/handler/shopservice/`
- Товары, покупки, платежи

**Новая структура (Node.js):**
```
services/shop/
├── shop.service.ts
├── actions/
│   ├── product/
│   │   ├── list.action.ts        # shop.product.list
│   │   └── get.action.ts         # shop.product.get
│   ├── purchase/
│   │   ├── prepare.action.ts     # shop.purchase.prepare
│   │   ├── payment.action.ts     # shop.purchase.payment
│   │   └── status.action.ts      # shop.purchase.status
│   └── inventory/
│       └── sync.action.ts        # shop.inventory.sync
├── entities/
│   ├── product.entity.ts
│   └── purchase.entity.ts
└── types/
    └── shop.types.ts
```

**Задачи:**
- [ ] Реализовать каталог товаров
- [ ] Реализовать flow покупки
- [ ] Интегрировать с payment service
- [ ] Интегрировать со storage (images)

---

### 4.8 Buyout Service

**Приоритет:** 8
**Сложность:** Высокая
**Риск:** Высокий (основной бизнес)

**Текущая реализация (Go):**
- `bot/api/handler/buyoutservice/`
- Сделки, подтверждения, выплаты

**Новая структура (Node.js):**
```
services/buyout/
├── buyout.service.ts
├── actions/
│   ├── deal/
│   │   ├── begin.action.ts       # buyout.deal.begin
│   │   ├── confirm.action.ts     # buyout.deal.confirm
│   │   └── status.action.ts      # buyout.deal.status
│   ├── payout/
│   │   ├── paynet.action.ts      # buyout.payout.paynet
│   │   └── sbp.action.ts         # buyout.payout.sbp
│   └── sms/
│       └── resend.action.ts      # buyout.sms.resend
├── workflows/
│   └── buyout.workflow.ts        # State machine
├── entities/
│   └── deal.entity.ts
└── types/
    └── buyout.types.ts
```

**Задачи:**
- [ ] Реализовать state machine сделки
- [ ] Интегрировать с evaluation service
- [ ] Интегрировать с payment service
- [ ] Интегрировать с document service
- [ ] Реализовать SMS подтверждение
- [ ] Обширное тестирование

---

### 4.9 Payment Service

**Приоритет:** 9 (последний из критичных)
**Сложность:** Очень высокая
**Риск:** Критический (финансы)

**Текущая реализация (Go):**
- `payout/rpc/pneservice/` - PaynetEasy
- `payout/rpc/sbpservice/` - SBP (RSB, Tinkoff)
- RSA подписи, callbacks

**Новая структура (Node.js):**
```
services/payment/
├── payment.service.ts
├── actions/
│   ├── paynet/
│   │   ├── init-payout.action.ts     # payment.paynet.initPayout
│   │   ├── init-payment.action.ts    # payment.paynet.initPayment
│   │   ├── check.action.ts           # payment.paynet.check
│   │   └── balance.action.ts         # payment.paynet.balance
│   └── sbp/
│       ├── init.action.ts            # payment.sbp.init
│       ├── check.action.ts           # payment.sbp.check
│       └── banks.action.ts           # payment.sbp.banks
├── providers/
│   ├── paynet/
│   │   ├── paynet.provider.ts
│   │   └── paynet.signer.ts          # RSA signing
│   └── sbp/
│       ├── rsb.provider.ts           # RSB provider
│       └── tinkoff.provider.ts       # Tinkoff provider
├── callbacks/
│   ├── paynet.callback.ts
│   └── sbp.callback.ts
├── checkers/
│   ├── payout.checker.ts             # Async status polling
│   └── payment.checker.ts
├── entities/
│   ├── payment.entity.ts
│   └── payout.entity.ts
└── types/
    └── payment.types.ts
```

**Критичные аспекты:**
- RSA подпись запросов
- Идемпотентность операций
- Retry логика с exponential backoff
- Точное логирование для audit
- Обработка callbacks

**Задачи:**
- [ ] Реализовать PaynetEasy provider
- [ ] Реализовать RSB provider
- [ ] Реализовать Tinkoff provider
- [ ] Портировать RSA signing
- [ ] Реализовать async status checkers (BullMQ)
- [ ] Callback handlers
- [ ] Extensive testing в sandbox
- [ ] Audit logging
- [ ] Dual-write с Go (период параллельной работы)

---

### 4.10 Admin Service

**Приоритет:** 10
**Сложность:** Средняя
**Риск:** Низкий

**Текущая реализация (Go):**
- `dash/` - Web UI, templates

**Новая структура (Node.js):**
```
services/admin/
├── admin.service.ts
├── actions/
│   ├── dashboard/
│   │   ├── stats.action.ts
│   │   └── health.action.ts
│   ├── users/
│   │   ├── list.action.ts
│   │   └── manage.action.ts
│   └── operators/
│       └── review.action.ts
├── web/
│   ├── routes.ts
│   └── views/                    # или SPA frontend
└── entities/
    └── user.entity.ts
```

**Задачи:**
- [ ] Реализовать dashboard API
- [ ] Портировать или переписать UI
- [ ] Интегрировать со всеми сервисами

---

## 5. Общие компоненты

### 5.1 Shared Libraries (npm packages)

```
packages/
├── @goldex/common/
│   ├── types/                    # Общие TypeScript типы
│   ├── enums/                    # Enums (status, alloy, etc.)
│   ├── utils/                    # Утилиты
│   └── validators/               # Общие валидаторы
│
├── @goldex/currency/
│   ├── currency.ts               # Currency enum и утилиты
│   ├── decimal.ts                # Decimal operations
│   └── format.ts                 # Форматирование
│
├── @goldex/fineness/
│   ├── alloy.ts                  # Alloy definitions
│   ├── fineness.ts               # Fineness calculations
│   └── spectrum.ts               # Spectrum parsing
│
├── @goldex/cost/
│   ├── estimator.ts              # Price estimation
│   └── pricer.ts                 # Pricer interface
│
└── @goldex/logging/
    ├── logger.ts                 # Pino/Winston wrapper
    └── influx.ts                 # InfluxDB metrics
```

### 5.2 Database Schema (TypeORM)

```typescript
// entities/bot.entity.ts
import { Entity, PrimaryGeneratedColumn, Column, OneToMany, ManyToOne } from "typeorm";

@Entity("bot_bots")
export class Bot {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ unique: true })
  uuid: string;

  @Column()
  orgId: number;

  @Column()
  name: string;

  @OneToMany(() => Session, session => session.bot)
  sessions: Session[];

  @ManyToOne(() => Org, org => org.bots)
  org: Org;
}

// entities/session.entity.ts
@Entity("bot_sessions")
export class Session {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  botId: number;

  @Column({ nullable: true })
  clientId: number;

  @Column({ type: "enum", enum: SessionStatus })
  status: SessionStatus;

  @ManyToOne(() => Bot, bot => bot.sessions)
  bot: Bot;

  @ManyToOne(() => Client, client => client.sessions, { nullable: true })
  client: Client;

  @OneToMany(() => Evaluation, eval => eval.session)
  evaluations: Evaluation[];
}

// entities/evaluation.entity.ts
@Entity("bot_evaluations")
export class Evaluation {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  sessionId: number;

  @Column({ type: "enum", enum: EvalStatus })
  status: EvalStatus;

  @Column({ type: "enum", enum: Alloy })
  alloy: Alloy;

  @Column({ type: "decimal", precision: 10, scale: 4 })
  weight: number;

  @Column()
  fineness: number;

  @ManyToOne(() => Session, session => session.evaluations)
  session: Session;

  @OneToMany(() => Photo, photo => photo.evaluation)
  photos: Photo[];

  @OneToOne(() => EvaluationCost, cost => cost.evaluation)
  cost: EvaluationCost;
}

// entities/client.entity.ts
@Entity("bot_clients")
export class Client {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  phone: string;

  @Column({ nullable: true })
  firstName: string;

  @Column({ nullable: true })
  lastName: string;

  @Column({ nullable: true })
  middleName: string;

  @Column({ type: "date", nullable: true })
  birthDate: Date;

  @Column({ nullable: true })
  passportSeries: string;

  @Column({ nullable: true })
  passportNumber: string;

  @OneToMany(() => Session, session => session.client)
  sessions: Session[];
}

// entities/deal.entity.ts
@Entity("bot_buyout_deals")
export class BuyoutDeal {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  sessionId: number;

  @Column({ type: "enum", enum: DealStatus })
  status: DealStatus;

  @Column({ type: "decimal", precision: 12, scale: 2 })
  amount: number;

  @Column({ type: "enum", enum: PaymentMethod })
  paymentMethod: PaymentMethod;

  @Column({ nullable: true })
  paymentId: string;

  @CreateDateColumn()
  createdAt: Date;

  @UpdateDateColumn()
  updatedAt: Date;
}

// entities/payment.entity.ts
@Entity("payout_pne_payments")
export class PnePayment {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  orderId: string;

  @Column({ type: "enum", enum: PaymentStatus })
  status: PaymentStatus;

  @Column({ type: "decimal", precision: 12, scale: 2 })
  amount: number;

  @Column({ type: "text", nullable: true })
  responseData: string;

  @CreateDateColumn()
  createdAt: Date;

  @UpdateDateColumn()
  updatedAt: Date;
}
```

### 5.3 TypeORM Data Source Configuration

```typescript
// database/data-source.ts
import { DataSource } from "typeorm";
import { Bot, Session, Client, Evaluation, BuyoutDeal } from "./entities";

export const AppDataSource = new DataSource({
  type: "mysql",
  host: process.env.DB_HOST || "localhost",
  port: parseInt(process.env.DB_PORT || "3306"),
  username: process.env.DB_USER || "root",
  password: process.env.DB_PASSWORD || "",
  database: process.env.DB_NAME || "goldex",
  synchronize: false, // Use migrations in production
  logging: process.env.NODE_ENV === "development",
  entities: [Bot, Session, Client, Evaluation, BuyoutDeal],
  migrations: ["database/migrations/*.ts"],
  subscribers: [],
});

// Moleculer DB Mixin with TypeORM
// mixins/typeorm.mixin.ts
import { ServiceSchema } from "moleculer";
import { AppDataSource } from "../database/data-source";

export function TypeORMMixin(entities: Function[]): Partial<ServiceSchema> {
  return {
    async started() {
      if (!AppDataSource.isInitialized) {
        await AppDataSource.initialize();
        this.logger.info("TypeORM DataSource initialized");
      }
    },

    methods: {
      getRepository(entity: Function) {
        return AppDataSource.getRepository(entity);
      }
    }
  };
}
```

### 5.4 Moleculer Configuration

```typescript
// moleculer.config.ts
import { BrokerOptions } from "moleculer";

const config: BrokerOptions = {
  namespace: "goldex",
  nodeID: process.env.NODE_ID,

  transporter: "nats://nats:4222",

  serializer: "JSON", // или Protobuf для совместимости

  cacher: {
    type: "Redis",
    options: {
      prefix: "GOLDEX",
      ttl: 30,
    }
  },

  logger: {
    type: "Pino",
    options: {
      level: "info",
    }
  },

  tracing: {
    enabled: true,
    exporter: {
      type: "Jaeger",
    }
  },

  metrics: {
    enabled: true,
    reporter: {
      type: "Prometheus",
    }
  },

  validator: "Fastest",

  circuitBreaker: {
    enabled: true,
    threshold: 0.5,
    minRequestCount: 20,
    windowTime: 60,
  },

  retryPolicy: {
    enabled: true,
    retries: 3,
    delay: 100,
    maxDelay: 2000,
    factor: 2,
  },

  requestTimeout: 10000,
};

export default config;
```

### 5.5 API Gateway

```typescript
// gateway.service.ts
import { ServiceSchema } from "moleculer";
import ApiGateway from "moleculer-web";

const GatewayService: ServiceSchema = {
  name: "gateway",
  mixins: [ApiGateway],

  settings: {
    port: 3000,

    routes: [
      {
        path: "/api/v1",

        authorization: true,

        aliases: {
          // Session
          "POST /session": "identity.session.begin",
          "POST /session/:id/authorized": "identity.session.authorize",
          "DELETE /session/:id": "identity.session.end",
          "POST /session/:id/phone/number": "identity.phone.send",
          "POST /session/:id/phone/verify": "identity.phone.verify",

          // Evaluation
          "POST /eval": "evaluation.begin",
          "POST /eval/:id/finished": "evaluation.finish",
          "GET /eval/:id/cost": "evaluation.cost",

          // Buyout
          "POST /buyout": "buyout.deal.begin",
          "POST /buyout/:id/confirm": "buyout.deal.confirm",
          "POST /buyout/:id/payout-paynet": "buyout.payout.paynet",
          "POST /buyout/:id/payout-sbp": "buyout.payout.sbp",
          "GET /buyout/:id/status": "buyout.deal.status",

          // Shop
          "GET /shop": "shop.product.list",
          "POST /shop": "shop.purchase.prepare",
          "POST /shop/:id/payment-paynet": "shop.purchase.payment",
          "GET /shop/:id/status": "shop.purchase.status",
        },

        bodyParsers: {
          json: { limit: "2MB" },
          urlencoded: { extended: true }
        },
      },

      // Goldex callbacks (no auth)
      {
        path: "/callback",
        authorization: false,
        aliases: {
          "POST /eval-photo": "evaluation.callback.photo",
        }
      }
    ],
  },

  methods: {
    authorize(ctx, route, req) {
      // JWT validation
    }
  }
};

export default GatewayService;
```

---

## 6. План работ по этапам

### Этап 0: Подготовка инфраструктуры

**Задачи:**
- [ ] Инициализировать monorepo (Turborepo/Nx)
- [ ] Настроить TypeScript конфигурацию
- [ ] Настроить ESLint, Prettier
- [ ] Создать базовый Moleculer проект
- [ ] Настроить Docker для разработки
- [ ] Настроить CI/CD pipeline
- [ ] Создать TypeORM entities (миграция GORM → TypeORM)
- [ ] Создать shared packages структуру

**Результат:** Рабочий boilerplate с одним тестовым сервисом

---

### Этап 1: Pricing + Storage Services

**Pricing Service:**
- [ ] Реализовать Goldex API клиент
- [ ] Реализовать pricing.gold action
- [ ] Реализовать pricing.silver action
- [ ] Настроить кэширование
- [ ] Unit тесты
- [ ] Integration тесты

**Storage Service:**
- [ ] Реализовать chunked upload
- [ ] Реализовать download
- [ ] Реализовать link generation
- [ ] Integration тесты

**Интеграция:**
- [ ] Настроить NATS bridge (Go ↔ Node.js)
- [ ] Переключить Go сервисы на Node.js pricing
- [ ] Мониторинг и логирование

---

### Этап 2: Document + Notification Services

**Document Service:**
- [ ] Портировать PDF шаблоны
- [ ] Реализовать PDF генерацию
- [ ] Реализовать OrangeData интеграцию
- [ ] RSA signing
- [ ] Очередь фискализации

**Notification Service:**
- [ ] Настроить Telegram bot
- [ ] Реализовать WebSocket сервер
- [ ] Подписка на события
- [ ] Шаблоны сообщений

---

### Этап 3: Evaluation + Identity Services

**Evaluation Service:**
- [ ] Портировать cost calculator
- [ ] Портировать fineness calculator
- [ ] Goldex callbacks
- [ ] Review workflow

**Identity Service:**
- [ ] Session management
- [ ] Client management
- [ ] Phone verification
- [ ] SMSC integration

---

### Этап 4: Shop + Buyout Services

**Shop Service:**
- [ ] Product catalog
- [ ] Purchase flow
- [ ] Payment integration

**Buyout Service:**
- [ ] Deal state machine
- [ ] SMS confirmation
- [ ] Payout integration
- [ ] Full workflow testing

---

### Этап 5: Payment Service

**PaynetEasy:**
- [ ] Provider implementation
- [ ] RSA signing
- [ ] Status checker
- [ ] Callbacks

**SBP:**
- [ ] RSB provider
- [ ] Tinkoff provider
- [ ] Status checker
- [ ] Callbacks

**Валидация:**
- [ ] Shadow testing (Go vs Node.js)
- [ ] Dual-write период
- [ ] Постепенное переключение трафика

---

### Этап 6: Admin Service + Финализация

**Admin Service:**
- [ ] Dashboard API
- [ ] User management
- [ ] Operator tools

**Финализация:**
- [ ] Отключение Go сервисов
- [ ] Performance tuning
- [ ] Documentation
- [ ] Runbooks

---

## 7. Риски и митигация

### 7.1 Технические риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Несовместимость протоколов (NRPC → Moleculer) | Средняя | Высокое | Protobuf serializer в Moleculer, bridge сервис |
| Потеря данных при миграции | Низкая | Критическое | Dual-write, backup стратегия |
| Расхождение бизнес-логики | Средняя | Высокое | Extensive тесты, shadow testing |
| Performance деградация | Средняя | Среднее | Load testing, caching, horizontal scaling |
| RSA signing несовместимость | Низкая | Высокое | Тестирование с prod sandbox |

### 7.2 Бизнес риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Downtime во время миграции | Средняя | Высокое | Blue-green deployment, rollback план |
| Финансовые потери (payment) | Низкая | Критическое | Payment service последний, extensive QA |
| Задержка сроков | Высокая | Среднее | Итеративный подход, MVP для каждого сервиса |

### 7.3 Чеклист готовности к production

**Для каждого сервиса:**
- [ ] Unit тесты (>80% coverage)
- [ ] Integration тесты
- [ ] Load тесты
- [ ] Security review
- [ ] Logging и tracing
- [ ] Метрики и алерты
- [ ] Документация API
- [ ] Runbook
- [ ] Rollback процедура

---

## Приложения

### A. Структура monorepo

```
goldex-backend/
├── apps/
│   ├── gateway/                  # API Gateway
│   └── admin-web/                # Admin SPA (optional)
│
├── services/
│   ├── pricing/
│   ├── storage/
│   ├── document/
│   ├── notification/
│   ├── evaluation/
│   ├── identity/
│   ├── shop/
│   ├── buyout/
│   ├── payment/
│   └── admin/
│
├── packages/
│   ├── @goldex/common/
│   ├── @goldex/currency/
│   ├── @goldex/fineness/
│   ├── @goldex/cost/
│   └── @goldex/logging/
│
├── database/
│   ├── data-source.ts
│   ├── entities/
│   └── migrations/
│
├── docker/
│   ├── docker-compose.yml
│   └── Dockerfile
│
├── .github/
│   └── workflows/
│
├── turbo.json
├── package.json
└── tsconfig.base.json
```

### B. Сравнение технологий

| Аспект | Go (текущий) | Node.js (целевой) |
|--------|--------------|-------------------|
| RPC | NRPC (protobuf) | Moleculer actions |
| Transport | NATS | NATS (native support) |
| ORM | GORM | TypeORM |
| Validation | proto rules | Zod / fastest-validator |
| DI | manual | Moleculer services |
| Config | Viper | @nestjs/config / dotenv |
| Logging | Logrus | Pino |
| PDF | gopdf | PDFKit / Puppeteer |
| HTTP | Chi | Moleculer-web |

### C. Полезные ссылки

- [Moleculer Documentation](https://moleculer.services/)
- [TypeORM Documentation](https://typeorm.io/)
- [NATS.io](https://nats.io/)
- [Turborepo](https://turbo.build/repo)
