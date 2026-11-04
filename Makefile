.PHONY: setup lint typecheck test data forecast backtest dashboard demo eval clean

setup:
	uv venv && uv pip install -e ".[dev]" && pre-commit install

lint:
	ruff check src tests scripts app

typecheck:
	mypy src

test:
	pytest

data:
	python scripts/generate.py

forecast:
	python scripts/run_forecast.py

backtest:
	python scripts/run_backtest.py

dashboard:
	streamlit run app/Home.py

demo: data forecast dashboard

eval:
	pytest -m eval tests/evals

clean:
	rm -rf data/raw/* data/processed/* outputs/runs/* .pytest_cache .ruff_cache .mypy_cache
