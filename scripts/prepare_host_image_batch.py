import argparse
import json

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.host_image_batch import prepare_host_image_batch


parser = argparse.ArgumentParser()
parser.add_argument("project_dir")
parser.add_argument("--episode", default="EP01")
parser.add_argument("--batch-dir")
parser.add_argument("--image-dir")
parser.add_argument("--width", type=int, default=1536)
parser.add_argument("--height", type=int, default=1024)
parser.add_argument("--quality", default="high", choices=("medium", "high"))
args = parser.parse_args()
result = prepare_host_image_batch(
    args.project_dir,
    episode_id=args.episode,
    batch_dir=args.batch_dir,
    image_dir=args.image_dir,
    width=args.width,
    height=args.height,
    quality=args.quality,
)
print(json.dumps(result, ensure_ascii=False, indent=2))
