import json
import logging
import os
from typing import Dict
import csv

import toml

logger = logging.getLogger(__name__)


def load_cog_toml(cog_path: str) -> Dict:
    """Load a cogs TOML file using a modules __name__ attribute as the key.

    Args:
        cog_path (str): The relative path of a module.

    Returns:
        Dict: A dictionary containng the key/value pairs defined in the cog's TOML file.
    """
    cog_name = os.path.splitext(cog_path)[-1][1:]
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "locale", f"{cog_name}.toml"))
    try:
        return toml.load(path)
    except FileNotFoundError:
        logger.warning(f"Unable to load TOML file for {cog_path}")
        return {}


def load_banned_words():
    """Load a text file where each line contains a banned word.

    Returns:
        list: A list of banned words.
    """
    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "banned_words.txt"))
    try:
        lines = []
        with open(file_path, "rt") as file:
            for line in file.readlines():
                if not line.startswith("#"):
                    lines.append(line.strip())
        return lines
    except FileNotFoundError:
        return []


def load_quotes() -> tuple[list[str], list[dict[str, any]]]:
    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "quotes.csv"))
    try:
        lines = []
        with open(file_path, "r") as f:
            reader = csv.reader(f)
            for line in reader:
                lines.append(line)

        labels = [x.lower() for x in lines.pop(0)]
        for idx, line in enumerate(lines):
            new_item = {}
            for idx_b, item in enumerate(line):
                new_item[labels[idx_b]] = item
            lines[idx] = new_item
        return labels, lines
    except FileNotFoundError:
        return [], [{}]
