.PHONY: setup lint typecheck test data forecast weekly backtest dashboard demo eval clean

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

demo: data weekly dashboard

eval:
	$(BIN)/pytest -m eval tests/evals

clean:
	rm -rf data/raw/* data/processed/* outputs/runs/* .pytest_cache .ruff_cache .mypy_cache
