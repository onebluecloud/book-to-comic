import argparse

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.project_workflow import export_project


parser = argparse.ArgumentParser()
parser.add_argument("project_dir")
parser.add_argument("--formats", default="pdf,cbz,epub,long-image,zip")
args = parser.parse_args()
for key, path in export_project(args.project_dir, formats=args.formats).items():
    print(f"{key}: {path}")
