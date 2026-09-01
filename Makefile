.PHONY: up down logs worker gate

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
