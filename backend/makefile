.PHONY: help install dev-install test lint format run migrate docker-up docker-down clean

help:
	@echo "Comandos disponíveis:"
	@echo "  install      - Instala dependências de produção"
	@echo "  dev-install  - Instala todas as dependências (incluindo dev)"
	@echo "  test         - Executa testes"
	@echo "  lint         - Executa linting do código"
	@echo "  format       - Formata o código"
	@echo "  run          - Inicia o servidor de desenvolvimento"
	@echo "  migrate      - Executa migrações do banco de dados"
	@echo "  docker-up    - Inicia containers Docker"
	@echo "  docker-down  - Para containers Docker"
	@echo "  clean        - Limpa arquivos temporários"

install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	pre-commit install

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	flake8 app/ tests/
	mypy app/

format:
	black app/ tests/
	isort app/ tests/

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic upgrade head

migrate-create:
	@read -p "Nome da migração: " name; \
	alembic revision --autogenerate -m "$$name"

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

# Comandos de banco de dados
db-create:
	docker-compose exec backend alembic upgrade head

db-seed:
	docker-compose exec backend python scripts/seed_database.py

db-reset:
	docker-compose exec backend alembic downgrade base
	docker-compose exec backend alembic upgrade head

# Comandos de produção
build:
	docker build -t climanegocios-backend:latest .

deploy:
	# Adicionar comandos de deploy aqui
	@echo "Deploy não configurado ainda"