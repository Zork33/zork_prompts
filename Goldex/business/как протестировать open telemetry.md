### Как включить и проверить OpenTelemetry в проекте

- Сервис поднимает OpenTelemetry SDK только если выставить `ENABLE_TRACING=true`; имя сервиса берётся из `SERVICE_NAME` (по умолчанию `business-v2`).
    

- При включении трейсинга вызывается `configureTracing`, который стартует `NodeSDK` с OTLP HTTP экспортёром и авто-инструментацией Node.js; диагностические логи OTel пишутся в консоль, что помогает увидеть, что экспортер запустился.
    

Запускайте сервис с переменными окружения, указывающими ваш приёмник трейсинга, например:

OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
ENABLE_TRACING=true
SERVICE_NAME=business-v2
deno task dev
    
- Для локальной проверки поднимите OTLP-совместимый приёмник, например OpenTelemetry Collector:
    

- `docker run --rm -p 4318:4318 otel/opentelemetry-collector-contrib`
    
    и проверьте, что при запросах к сервису в логах коллектора появляются спаны с именем `business-v2`.
    
- Если нужно более детальное логирование и отладка экспорта, можно поднять уровень логов OTel через `OTEL_LOG_LEVEL=debug` — диагностика выводится в консоль благодаря `DiagConsoleLogger`.