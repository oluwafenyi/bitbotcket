import os
import sys
import time
from typing import Dict, Tuple
from datetime import datetime

import dotenv
import requests.exceptions
from slack_sdk import WebClient

from safe_scheduler import SafeScheduler
from comment import Comment
from bitbucket import Bitbucket, UnauthorizedBitbucketUserException


dotenv.load_dotenv()

BITBUCKET_USERNAME = os.environ["BITBUCKET_USERNAME"]
BITBUCKET_APP_PASSWORD = os.environ["BITBUCKET_APP_PASSWORD"]
BITBUCKET_WORKSPACES = os.environ["BITBUCKET_WORKSPACES"].split(",") if os.environ["BITBUCKET_WORKSPACES"] != "" else []
SLACK_TOKEN = os.environ["SLACK_TOKEN"]
SLACK_CHANNEL = os.environ["SLACK_CHANNEL"]
WHEN_TO_RUN = os.environ["WHEN_TO_RUN"]


def build_comment_tree(comment_list: list) -> Comment:
    base = Comment(0)
    comment_map: Dict[int, Comment] = {}

    for comment in comment_list:
        c = Comment(comment["id"], comment["content"]["html"], comment["user"]["account_id"], comment["user"]["display_name"])
        comment_map[c.id_] = c

    for comment in comment_list:
        if comment.get("parent"):
            parent = comment_map[comment["parent"]["id"]]
            child = comment_map[comment["id"]]
            parent.add_child(child)
        else:
            base.add_child(comment_map[comment["id"]])
    return base


def find_unanswered_comments(comment_tree: Comment, unanswered_comments: dict = None, user_map: dict = None) -> Tuple[Dict[str, int], Dict[str, str]]:
    comment_mentions = comment_tree.mentions
    comment_repliers = {c.creator_id: c for c in comment_tree.children.values()}
    for user_id in comment_mentions:
        if user_id not in comment_repliers:
            unanswered_comments.setdefault(user_id, 0)
            unanswered_comments[user_id] += 1
            user_map[user_id] = comment_mentions[user_id]
    for child_id, child_comment in comment_tree.children.items():
        find_unanswered_comments(child_comment, unanswered_comments, user_map)
    return unanswered_comments, user_map


def generate_unanswered_comments_report(unanswered_comments: Dict[str, int], user_map: Dict[str, str]):
    text = ""
    for user_id, number_of_comments in unanswered_comments.items():
        text += f"{user_map[user_id]} has {number_of_comments} unanswered {'comment' if number_of_comments == 1 else 'comments'}\n"
    return text


def main(bit: Bitbucket, slack_client: WebClient):
    print(f"running script: {datetime.now().strftime('%m/%d/%Y, %H:%M:%S')}")
    user_map: Dict[str, str] = {}
    unanswered_comments: Dict[str, int] = {}

    workspaces_ids = [ws["workspace"]["uuid"] for ws in bit.get_current_user_workspaces()] if len(BITBUCKET_WORKSPACES) == 0 else BITBUCKET_WORKSPACES
    for workspace_id in workspaces_ids:
        for repository in bit.get_repositories_from_workspace(workspace_id):
            for pr in bit.get_pull_requests(workspace_id, repository["uuid"]):
                comments = bit.get_pull_request_comments(workspace_id, repository["uuid"], pr["id"])
                tree = build_comment_tree(comments)
                unanswered_comments, user_map = find_unanswered_comments(tree, unanswered_comments, user_map)

    text = generate_unanswered_comments_report(unanswered_comments, user_map)
    slack_client.chat_postMessage(channel=SLACK_CHANNEL, text=text)
    print("script ran successfully")


if __name__ == "__main__":
    bit = Bitbucket(username=BITBUCKET_USERNAME, app_password=BITBUCKET_APP_PASSWORD)
    try:
        bit.auth_test()
    except (UnauthorizedBitbucketUserException, requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
        print("Could not authenticate with Bitbucket:", e)
        sys.exit(1)

    slack_client = WebClient(token=SLACK_TOKEN)
    auth_response = slack_client.auth_test()
    if not auth_response.data["ok"]:
        print("Could not authenticate with slack.")
        sys.exit(2)

    schedule = SafeScheduler(minutes_after_failure=5)
    schedule.every().day.at(WHEN_TO_RUN).do(main, bit, slack_client)

    print("running, next job scheduled for:", schedule.next_run.strftime("%m/%d/%Y, %H:%M:%S"))

    while True:
        schedule.run_pending()
        time.sleep(1)
