""" does the healthcheck, doesn't need curl """

import sys

import urllib.request
import urllib.error

import click

DEFAULT_URL = "http://localhost:11707/up"

@click.command()
@click.argument("url", default=DEFAULT_URL)
def cli(url: str=DEFAULT_URL):
    """ Checks the URL works """
    try:
        with urllib.request.urlopen(url) as f:
            result = f.read().decode('utf-8')
            if result == "OK":
                print("OK")
                sys.exit(0)
            else:
                print(f"Failed to get 'OK' response: {result}")
                sys.exit(1)
    except urllib.error.URLError as error_message:
        print(f"Error: {error_message}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    cli()
