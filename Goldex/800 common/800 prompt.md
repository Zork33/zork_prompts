[[Molecular сервис]]

добавить в промпт:

	Реализуй HTTP-сервер на Node.js только на встроенном модуле http (без Express и других библиотек).
	
	Требования к методу health:
	- endpoint: GET /healthz
	- ответ: 200 OK и JSON вида { "status": "ok", "version": "<значение из SERVICE_VERSION>", "uptimeSeconds": <process.uptime()>, "timestamp": "<ISO8601>" }
	- SERVICE_VERSION брать из переменной окружения (если нет — использовать "0.0.1")
	- заголовки: Content-Type: application/json, Cache-Control: no-store
	- любые другие пути должны возвращать 404 Not Found (text/plain)
	
	Этот endpoint будет использоваться Kubernetes для liveness/readiness проверок, поэтому обработка должна быть максимально лёгкой и быстрой.
