import csv
import logging
import math
import os
import subprocess
from typing import Dict
from uuid import uuid4

import toml

MAX_FILE_BYTES = 25_000_000
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


def stitch_videos(video_list: list[str], output_file: str | None = None) -> str | None:
    base_path = os.path.abspath(os.path.curdir)
    videos_file = os.path.join(base_path, f"{uuid4()}.txt")
    with open(videos_file, "w") as f:
        for video in video_list:
            if not os.path.isabs(video):
                video = os.path.join(base_path, video)
            f.write(f"file '{video}'\n")

    if not output_file:
        output_file = f"{uuid4()}.mp4"

    if os.path.isabs(output_file):
        output_file = os.path.join(base_path, output_file)

    try:
        subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", videos_file, "-c", "copy", output_file], check=True)
        os.remove(videos_file)
        return output_file
    except subprocess.CalledProcessError:
        os.remove(videos_file)
        return None


def reduce_video(video_file: str, output_file: str | None = None) -> str | None:

    def get_crf(file_size):
        result = 21 + 25 * math.log(file_size / MAX_FILE_BYTES, 2)
        return round(result, 1)

    if not os.path.isabs(video_file):
        video_file = os.path.join(os.path.abspath(os.path.curdir), video_file)

    file_size = os.path.getsize(video_file)
    if file_size < MAX_FILE_BYTES:
        return video_file

    if not output_file:
        output_file = os.path.join(os.path.abspath(os.path.curdir), f"{uuid4()}.mp4")

    video_crf = get_crf(file_size)
    if video_crf < 0 or video_crf > 51:
        return None

    try:
        subprocess.run(["ffmpeg", "-i", video_file, "-vcodec", "libx264", "-crf", f"{video_crf!s}", output_file])
        os.remove(video_file)
        os.rename(output_file, video_file)
        return video_file
    except subprocess.CalledProcessError:
        return None
