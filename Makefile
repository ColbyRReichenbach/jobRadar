local-env:
	./scripts/setup_local_env.sh .env.local

local-open:
	./scripts/open_local_app.sh .env.local

local-up:
	docker compose up --build -d

local-down:
	docker compose down

local-logs:
	docker compose logs -f backend worker beat dashboard

local-reset:
	docker compose down -v

local-ps:
	docker compose ps
