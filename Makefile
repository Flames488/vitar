.PHONY: up down logs ps prod-up prod-down

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

prod-up:
	docker compose --profile observability -f docker-compose.yml -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose --profile observability -f docker-compose.yml -f docker-compose.prod.yml down
