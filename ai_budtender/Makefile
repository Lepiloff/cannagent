.PHONY: help build start stop restart logs test clean migration init-db

# Default target
help:
	@echo "Available commands:"
	@echo "  build        - Build Docker images"
	@echo "  start        - Start all services"
	@echo "  stop         - Stop all services"  
	@echo "  restart      - Restart all services"
	@echo "  logs         - Show logs"
	@echo "  test         - Run tests"
	@echo "  clean        - Clean up containers and volumes"
	@echo "  migration    - Create new database migration"
	@echo "  init-db      - Initialize database with migrations"
	@echo "  shell        - Open shell in API container"
	@echo "  redis-cli    - Open Redis CLI"

# Build Docker images
build:
	docker-compose build

# Start all services
start:
	@if [ ! -f .env ]; then \
		echo "Creating .env file from example..."; \
		cp env.example .env; \
		echo "✅ .env file created. Please edit it if needed."; \
	fi
	docker-compose up -d

# Stop all services
stop:
	docker-compose down

# Restart all services
restart: stop start

# Show logs
logs:
	docker-compose logs -f

# Run tests
test:
	docker-compose exec api pytest -v

# Clean up containers and volumes
clean:
	docker-compose down -v
	docker system prune -f

# Create new database migration
migration:
	docker-compose exec api alembic revision --autogenerate -m "$(MSG)"

# Initialize database with migrations
init-db:
	docker-compose exec api python scripts/init_db.py

# Open shell in API container
shell:
	docker-compose exec api bash

# Open Redis CLI
redis-cli:
	docker-compose exec redis redis-cli

# Install dependencies locally (for development)
install:
	pip install -r requirements.txt

# Run application locally (for development)
dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Format code
format:
	black app/ tests/
	isort app/ tests/

# Lint code
lint:
	flake8 app/ tests/
	mypy app/

# Security scan
security:
	bandit -r app/

# Generate requirements.txt
freeze:
	pip freeze > requirements.txt

# Backup database
backup:
	docker-compose exec db pg_dump -U user ai_budtender > backup.sql

# Restore database
restore:
	docker-compose exec -T db psql -U user ai_budtender < backup.sql 