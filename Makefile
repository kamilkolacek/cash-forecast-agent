.PHONY: setup lint typecheck test data forecast weekly backtest dashboard demo demo-data eval clean

# Call tools from the project venv directly, so nothing needs activating first.
BIN := .venv/bin

setup:
	uv venv --allow-existing && uv pip install -e ".[dev]" && $(BIN)/pre-commit install

lint:
	$(BIN)/ruff check src tests scripts app

typecheck:
	$(BIN)/mypy src

test:
	$(BIN)/pytest

data:
	$(BIN)/python scripts/generate.py

forecast:
	$(BIN)/python scripts/run_forecast.py

weekly:
	$(BIN)/python scripts/run_weekly.py

backtest:
	$(BIN)/python scripts/run_backtest.py

dashboard:
	$(BIN)/streamlit run app/Home.py

# One command from a fresh clone: data, a live run, a run 4 weeks later (with a real
# variance story), the accuracy report, then the dashboard.
demo-data: data
	$(BIN)/python scripts/run_weekly.py
	$(BIN)/python scripts/run_weekly.py --simulate-week 4
	-$(BIN)/python scripts/run_backtest.py

demo: demo-data dashboard

eval:
	$(BIN)/pytest -m eval tests/evals -v

clean:
	rm -rf data/raw/* data/processed/* outputs/runs/* .pytest_cache .ruff_cache .mypy_cache
