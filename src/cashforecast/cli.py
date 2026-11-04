"""Command-line entry point: `cashforecast <command>`."""

from __future__ import annotations

import typer

from cashforecast import __version__
from cashforecast.config import load_entities, load_forecast_settings

app = typer.Typer(help="Cash Forecast Agent CLI", no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def check_config() -> None:
    """Validate config files and print a summary."""
    settings = load_forecast_settings()
    entities = load_entities()
    typer.echo(
        f"Config OK: {settings.horizon_weeks}-week horizon, "
        f"{settings.daily_detail_weeks} daily weeks, "
        f"entities={','.join(e.code for e in entities)}"
    )


if __name__ == "__main__":
    app()
