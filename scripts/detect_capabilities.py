from _bootstrap import add_project_root

add_project_root()
from book_to_comic.capabilities import capabilities_json

print(capabilities_json(), end="")
