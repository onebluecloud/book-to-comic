import argparse

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.project_workflow import validate_project


parser = argparse.ArgumentParser()
parser.add_argument("project_dir")
args = parser.parse_args()
errors = validate_project(args.project_dir)
if errors:
    print("\n".join(errors))
    raise SystemExit(1)
print("valid")
