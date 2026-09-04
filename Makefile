.PHONY: up down logs worker gate bridge

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

worker:
	python orchestration/worker.py

gate:
	python eval/braintrust/eval.config.py

# specs/002-webhook-trigger-bridge: relays GitHub webhook deliveries to the
# local bridge server. Both legs run as siblings under one trap/wait so a
# dead smee-client leg fails the target instead of leaving the bridge
# orphaned and silently unreachable.
bridge:
	@trap 'kill 0 2>/dev/null' EXIT INT TERM; \
	npx smee-client --url "$$WEBHOOK_PROXY_URL" --target "http://localhost:$${BRIDGE_PORT:-3000}/webhook" & smee_pid=$$!; \
	python -m orchestration.webhook_bridge.server & server_pid=$$!; \
	while kill -0 $$smee_pid 2>/dev/null && kill -0 $$server_pid 2>/dev/null; do sleep 1; done; \
	if ! kill -0 $$smee_pid 2>/dev/null; then \
		echo "bridge: smee-client relay exited — killing bridge server" >&2; \
		kill $$server_pid 2>/dev/null; \
		exit 1; \
	fi; \
	wait $$server_pid
