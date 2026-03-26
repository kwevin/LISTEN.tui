#!/usr/bin/env python3

# https://github.com/yt-dlp/yt-dlp/blob/master/devscripts/cli_to_api.py
# Modified for usage
import sys
from typing import Any

import yt_dlp
import yt_dlp.options


def __parse_patched_options(opts):
    create_parser = yt_dlp.options.create_parser
    patched_parser = create_parser()
    patched_parser.defaults.update(
        {
            "ignoreerrors": False,
            "retries": 0,
            "fragment_retries": 0,
            "extract_flat": False,
            "concat_playlist": "never",
        }
    )
    yt_dlp.options.create_parser = lambda: patched_parser
    try:
        return yt_dlp.parse_options(opts)
    finally:
        yt_dlp.options.create_parser = create_parser


def cli_to_api(opts: list[str], cli_defaults: bool = False) -> dict[str, Any]:
    default_opts = __parse_patched_options([]).ydl_opts
    parsed = (yt_dlp.parse_options if cli_defaults else __parse_patched_options)(opts).ydl_opts

    diff = {k: v for k, v in parsed.items() if default_opts[k] != v}
    if "postprocessors" in diff:
        diff["postprocessors"] = [pp for pp in diff["postprocessors"] if pp not in default_opts["postprocessors"]]  # type: ignore
    return diff


if __name__ == "__main__":
    from pprint import pprint

    print("\nThe arguments passed translate to:\n")
    pprint(cli_to_api(sys.argv[1:]))
    print("\nCombining these with the CLI defaults gives:\n")
    pprint(cli_to_api(sys.argv[1:], True))
