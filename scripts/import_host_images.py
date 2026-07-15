import argparse
import json

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.image_assets import import_host_image_panels


parser = argparse.ArgumentParser()
parser.add_argument("project_dir")
parser.add_argument("--image-dir", required=True)
parser.add_argument("--episode", default="EP01")
parser.add_argument("--min-width", type=int, default=900)
parser.add_argument("--min-height", type=int, default=600)
parser.add_argument("--min-file-bytes", type=int, default=100_000)
args = parser.parse_args()
result = import_host_image_panels(
    args.project_dir,
    args.image_dir,
    episode_id=args.episode,
    min_width=args.min_width,
    min_height=args.min_height,
    min_file_bytes=args.min_file_bytes,
)
print(json.dumps(result, ensure_ascii=False, indent=2))
