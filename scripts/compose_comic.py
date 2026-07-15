import argparse

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.project_workflow import compose_project


parser = argparse.ArgumentParser()
parser.add_argument("project_dir")
args = parser.parse_args()
for key, path in compose_project(args.project_dir).items():
    print(f"{key}: {path}")
