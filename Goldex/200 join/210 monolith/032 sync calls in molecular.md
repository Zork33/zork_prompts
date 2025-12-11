Коротко: **по‑настоящему “синхронных” (блокирующих) запросов в Moleculer нет и не нужно**, всё делается через `async/await` поверх `broker.call` / `ctx.call`. Но по коду это выглядит как обычный синхронный вызов.

---

### Базовая идея

В Moleculer вызов экшена делается так:

```js
const res = await broker.call("users.get", { id: 5 });
```

`broker.call` возвращает `Promise`. ([moleculer.services](https://moleculer.services/docs/0.14/actions.html?utm_source=chatgpt.com "Actions"))  
Когда ты пишешь `await`, код **ждёт результат** этого вызова, и только потом идёт дальше — для тебя это “синхронно”, хотя под капотом это асинхронный I/O.

То же самое внутри сервисов:

```js
actions: {
  async getUserWithPosts(ctx) {
    const user = await ctx.call("users.get", { id: ctx.params.id });
    const posts = await ctx.call("posts.list", { userId: ctx.params.id });

    return { user, posts };
  }
}
```

---

### “Синхронная” последовательность запросов

Если нужно строго по очереди (А → потом B → потом C):

```js
module.exports = {
  name: "pipeline",
  actions: {
    async run(ctx) {
      const a = await ctx.call("serviceA.action", { x: 1 });
      const b = await ctx.call("serviceB.action", { fromA: a });
      const c = await ctx.call("serviceC.action", { fromB: b });

      return { a, b, c };
    }
  }
};
```

Пока не придёт ответ из `serviceA.action`, код до `serviceB.action` не дойдёт.

---

### Параллельные запросы (для сравнения)

Если тебе как раз **не** нужно синхронно, а хочешь параллельно:

```js
const [user, posts] = await Promise.all([
  ctx.call("users.get", { id: ctx.params.id }),
  ctx.call("posts.list", { userId: ctx.params.id })
]);
```

---

### Вызов из “обычного” Node‑скрипта

Если у тебя не сервис, а просто `index.js`, можно так:

```js
const { ServiceBroker } = require("moleculer");

const broker = new ServiceBroker();

(async () => {
  await broker.start();

  const res = await broker.call("greeter.hello", { name: "World" });
  console.log(res);

  await broker.stop();
})();
```

---

### Важные моменты

1. **Полностью блокирующего sync API нет** – только промисы + `async/await`. Это стандартный подход в Node.js и Moleculer.
    
2. Таймаут “синхронного” ожидания настраивается через:
    
    - глобально: `requestTimeout` в `ServiceBroker` ([moleculer.services](https://moleculer.services/docs/0.14/broker.html?utm_source=chatgpt.com "Broker"))
        
    - на конкретный вызов: `broker.call("svc.act", params, { timeout: 2000 })` ([moleculer.services](https://moleculer.services/docs/0.14/actions.html?utm_source=chatgpt.com "Actions"))
        
3. Внутри сервиса лучше использовать `ctx.call`, а не `broker.call`, чтобы сохранять контекст (meta, tracing и т.д.).
    

---

Если скажешь, **где именно** тебе нужны “синхронные” запросы (внутри одного сервиса, между несколькими, или из внешнего HTTP‑API) — я набросаю точный шаблон под твой случай.