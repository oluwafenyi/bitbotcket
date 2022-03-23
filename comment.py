
from bs4 import BeautifulSoup


class Comment:
    id_: int
    children: dict
    mentions: dict
    creator_id: str
    creator_display_name: str

    def __init__(self, id_: int, content="", creator_id="", creator_display_name=""):
        self.id_ = id_
        self.children = {}
        self.mentions = {}
        self.creator_id = creator_id
        self.creator_display_name = creator_display_name

        soup = BeautifulSoup(content, "html.parser")
        for selection in soup.select(".ap-mention"):
            user_id = selection.attrs["data-atlassian-id"]
            self.mentions[user_id] = selection.text.lstrip("@")

    def add_child(self, comment):
        self.children[comment.id_] = comment
