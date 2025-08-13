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

	@echo "  sync-strains    - Sync strains from cannamente (PRIMARY METHOD)"
	@echo "  status          - Show service status"
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
	@echo "🚀 Starting AI Budtender with local database..."
	docker-compose up -d
	@echo "⏳ Waiting for services to be ready..."
	sleep 10
	@echo "🔍 Checking system health..."
	make check-db

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
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

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

# Check database connection
check-db:
	@echo "Checking connection to database..."
	@docker compose exec api python -c "from app.db.database import SessionLocal; from app.db.repository import StrainRepository; session = SessionLocal(); repo = StrainRepository(session); strains = repo.get_strains(limit=5); print(f'✅ Database OK - {len(strains)} strains available'); session.close()"

# Show service status
status:
	@echo "Service Status:"
	@echo "API: http://localhost:8001"
	@echo "Metrics: http://localhost:9091"
	@echo "Redis: localhost:6380"
	@echo "External DB: localhost:5432 (cannamente)"
	@echo "Local DB: localhost:5433 (ai_budtender)"
	@echo ""
	@docker compose ps

# Sync strains from cannamente - PRIMARY METHOD
sync-strains:
	@echo "🔄 Syncing strains with structured data from cannamente..."
	@echo "This will sync feelings, helps_with, negatives, flavors and regenerate embeddings"
	docker compose exec api python scripts/sync_strain_relations.py 