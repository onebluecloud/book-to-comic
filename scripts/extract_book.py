import argparse

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.project_workflow import extract_book_to_project


parser = argparse.ArgumentParser()
parser.add_argument("input")
parser.add_argument("--output", required=True)
args = parser.parse_args()
print(extract_book_to_project(args.input, args.output))
