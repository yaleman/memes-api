""" CLI interface / main interface to memes-api """

import sys

import click
import uvicorn  # type: ignore


@click.command()
@click.option("--host", type=str, default="0.0.0.0")
@click.option("--port", type=int, default=8000)
@click.option("--proxy-headers", is_flag=True, help="Turn on proxy headers")
@click.option("--reload", is_flag=True)
def cli(
    host: str = "0.0.0.0",
    port: int = 8000,
    proxy_headers: bool = False,
    reload: bool = False,
) -> None:
    """server"""
    print(f"{proxy_headers=}", file=sys.stderr)
    print(f"{reload=}", file=sys.stderr)
    uvicorn_args = {
        "app": "memes_api:app",
        "reload": reload,
        "host": host,
        "port": port,
        "proxy_headers": proxy_headers,
    }
    if proxy_headers:
        uvicorn_args["forwarded_allow_ips"] = "*"
    uvicorn.run(**uvicorn_args)


if __name__ == "__main__":
    cli()
