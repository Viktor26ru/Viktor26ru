.PHONY: validate pg-checks pg-up pg-down pg-reset ci-local prototype-test demo-flow ops-test ops-run

validate:
	bash scripts/validate_artifacts.sh

pg-checks:
	DATABASE_URL=postgresql://postgres:postgres@localhost:5432/messenger_mvp bash scripts/run_pg_checks.sh

pg-up:
	docker compose up -d postgres

pg-down:
	docker compose down

pg-reset:
	docker compose down -v
	docker compose up -d postgres

ci-local: validate pg-checks

prototype-test:
	python -m unittest discover -s tests -p "test_*.py"

demo-flow:
	PYTHONPATH=. python scripts/demo_working_flow.py

ops-test:
	python3 -m unittest tests.test_ops_control

ops-run:
	python3 ops_control/app.py --daemon
