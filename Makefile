.PHONY: demo up down deploy-good deploy-broken deploy-fixed test signoz-up

demo:
	docker compose up -d --build
	python3 scripts/wait_for_demo.py
	python3 scripts/deploy.py good --compose --run

up:
	docker compose up -d --build
	python3 scripts/wait_for_demo.py

down:
	docker compose down

deploy-good:
	python3 scripts/deploy.py good --compose --run

deploy-broken:
	python3 scripts/deploy.py broken --compose --run

deploy-fixed:
	python3 scripts/deploy.py fixed --compose --run

test:
	python3 -m pytest backend/tests ../regressionforge-demo-store/backend/tests
	cd frontend && npm run lint && npm run build
	cd ../regressionforge-demo-store/frontend && npm run lint && npm run build

signoz-up:
	foundryctl cast -f observability/casting.yaml

