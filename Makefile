.PHONY: setup lint typecheck test data forecast weekly backtest dashboard demo demo-data eval clean

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

weekly:
	python scripts/run_weekly.py

backtest:
	python scripts/run_backtest.py

dashboard:
	streamlit run app/Home.py

# One command from a fresh clone: data, a live run, a run 4 weeks later (with a real
# variance story), the accuracy report, then the dashboard.
demo-data: data
	python scripts/run_weekly.py
	python scripts/run_weekly.py --simulate-week 4
	-python scripts/run_backtest.py

demo: demo-data dashboard

eval:
	pytest -m eval tests/evals -v

clean:
	rm -rf data/raw/* data/processed/* outputs/runs/* .pytest_cache .ruff_cache .mypy_cache
