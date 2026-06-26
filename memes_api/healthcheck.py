""" does the healthcheck, doesn't need curl """

import urllib.request
import urllib.error

import click

DEFAULT_URL = "http://localhost:11707/up"


@click.command()
@click.argument("url", default=DEFAULT_URL)
def cli(url: str = DEFAULT_URL) -> None:
    """Checks the URL works"""
    try:
        with urllib.request.urlopen(url) as response:
            result = response.read().decode("utf-8")
            if result == "OK":
                print("OK")
                return
            else:
                print(f"Failed to get 'OK' response: {result}")
                return
    except urllib.error.URLError as error_message:
        print(f"Error: {error_message}")
        return


if __name__ == "__main__":
    cli()
