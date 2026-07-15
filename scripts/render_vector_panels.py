import argparse

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.project_workflow import render_project


parser = argparse.ArgumentParser()
parser.add_argument("project_dir")
args = parser.parse_args()
for path in render_project(args.project_dir, image_backend="vector"):
    print(path)
