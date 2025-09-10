PY?=python3

.PHONY: venv run-naive run-queue fast-clients slow-client demo-naive demo-queue test fmt

venv:
	@echo "Creating virtual environment..."
	$(PY) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo "Virtual environment created. Activate with: source .venv/bin/activate"

run-naive:
	@echo "Starting server in naive mode..."
	$(PY) server.py --mode naive --rate 100

run-queue:
	@echo "Starting server in queue mode..."
	$(PY) server.py --mode queue --rate 100 --maxsize 100

fast-clients:
	@echo "Starting 3 fast clients for 30s..."
	$(PY) clientsim.py --concurrency 3 --duration 30 --id-prefix cli-fast

slow-client:
	@echo "Starting 1 slow client for 30s..."
	$(PY) clientsim.py --concurrency 1 --slow-ms 200 --duration 30 --id-prefix cli-slow

demo-naive:
	@echo "=== NAIVE MODE DEMO ==="
	@echo "Run these commands in separate terminals:"
	@echo "Terminal 1: make run-naive"
	@echo "Terminal 2: make fast-clients"
	@echo "Terminal 3: make slow-client"
	@echo "Watch how the slow client affects all clients in naive mode!"

demo-queue:
	@echo "=== QUEUE MODE DEMO ==="
	@echo "Run these commands in separate terminals:"
	@echo "Terminal 1: make run-queue"
	@echo "Terminal 2: make fast-clients" 
	@echo "Terminal 3: make slow-client"
	@echo "Notice how fast clients remain unaffected in queue mode!"

test:
	@echo "Running tests..."
	$(PY) -m pytest -q

fmt:
	@echo "Code formatting (placeholder)"
	@# Add black/ruff commands here if available
	@# $(PY) -m black .
	@# $(PY) -m ruff check --fix .