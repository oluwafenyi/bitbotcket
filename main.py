import os
import sys
import time
from typing import Dict, Tuple, List, Set
from datetime import datetime, timedelta

import dotenv
import requests.exceptions
from slack_sdk import WebClient

from safe_scheduler import SafeScheduler
from comment import Comment
from bitbucket import Bitbucket, UnauthorizedBitbucketUserException


dotenv.load_dotenv(".env")

BITBUCKET_USERNAME = os.environ["BITBUCKET_USERNAME"]
BITBUCKET_APP_PASSWORD = os.environ["BITBUCKET_APP_PASSWORD"]
BITBUCKET_WORKSPACES = os.environ["BITBUCKET_WORKSPACES"].split(",") if os.environ["BITBUCKET_WORKSPACES"] != "" else []
SLACK_TOKEN = os.environ["SLACK_TOKEN"]
SLACK_CHANNEL = os.environ["SLACK_CHANNEL"]
WHEN_TO_RUN = os.environ["WHEN_TO_RUN"]
REPO_SLUG = os.environ.get("REPO_SLUG", None)
RUN_IMMEDIATELY = os.environ.get("RUN_IMMEDIATELY", None)
PR_MAX_AGE_DAYS = os.environ.get("PR_MAX_AGE", "30")

DAYS_AGO = (datetime.now() - timedelta(days=int(PR_MAX_AGE_DAYS))).replace(hour=0, minute=0, second=0, microsecond=0)


def build_comment_tree(comment_list: list) -> Comment:
    """
    :param comment_list: comment data as gotten from the bitbucket pr comments API
    :returns: comments structured into a Comment object
    """

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


def find_pull_request_metrics(comment_tree: Comment, comment_url: str = None) -> Tuple[Dict[str, List[str]], Dict[str, str], Set[str], Set[str]]:
    """
    :param comment_tree: pull request comment tree representation
    :param comment_url: base_url for pull request
    :returns: tuple[dict=user_map, dict_unanswered_comments, set=participators, set=commenter_makers]
    """

    user_map = {}  # map of user account_id to Display Name
    unanswered_comments = {}  # map of user account_id to list of comments(urls) they have been mentioned in but did not reply
    participators = set()  # set of comment participators that got a reply from someone that isn't them
    stack = [comment_tree]
    comment_makers = set()

    while len(stack) > 0:
        comment = stack.pop(0)
        comment_mentions = comment.mentions
        comment_repliers = {c.creator_id: c for c in comment.children.values()}

        if comment.id_ != 0:
            comment_makers.add(comment.creator_id)
            if len(comment_repliers) > 1:
                participators.add(comment.creator_id)
            elif len(comment_repliers) == 1 and comment.creator_id not in comment_repliers:
                participators.add(comment.creator_id)

        for user_id in comment_mentions:
            if user_id not in comment_repliers:
                unanswered_comments.setdefault(user_id, [])
                unanswered_comments[user_id].append(comment_url + "#comment-{}".format(comment.id_))
                user_map[user_id] = comment_mentions[user_id]
        for child_comment in comment.children.values():
            stack.append(child_comment)

    return unanswered_comments, user_map, participators, comment_makers


def generate_report(unanswered_comments: Dict[str, List[str]], user_map: Dict[str, str], participation: Dict[str, int], pr_authors: Set[str], comment_makers_combined: Set[str]) -> str:
    """
    :param unanswered_comments:
    :param user_map:
    :param participation:
    :param author_participation:
    :returns: metrics reported in Markdown text
    """

    text = ""
    for user_id, unanswered in unanswered_comments.items():
        text += f"{user_map[user_id]} has {len(unanswered)} unanswered {'comment' if len(unanswered) == 1 else 'comments'}: "
        text += ",".join(["<{}|{}>".format(l, i + 1) for i, l in enumerate(unanswered)])
        text += "\n"
    else:
        text += ""

    text += "\n"

    max_participation = max(participation.values() or [0])
    for user_id, prs_participated_in in participation.items():
        text += f"{user_map[user_id]} engaged a conversation in {prs_participated_in} {'PR' if prs_participated_in == 1 else 'PRs'}"
        if prs_participated_in == max_participation:
            text += " (winner)"
        text += "\n"
    else:
        text += ""

    text += "\n"

    non_participating_authors = pr_authors.difference(comment_makers_combined)
    if len(non_participating_authors) > 0:
        text += f"The following users did not comment on any PR: {', '.join(user_map[a] for a in non_participating_authors)}\n"
    return text


def main(bit: Bitbucket, slack_client: WebClient):
    print(f"running script: {datetime.now().strftime('%m/%d/%Y, %H:%M:%S')}")
    user_map_combined: Dict[str, str] = {}
    unanswered_comments_combined: Dict[str, List[str]] = {}
    participation: Dict[str, int] = {}
    pr_authors: Set[str] = set()
    comment_makers_combined: Set[str] = set()

    workspaces_ids = [ws["workspace"]["uuid"] for ws in bit.get_current_user_workspaces()] if len(BITBUCKET_WORKSPACES) == 0 else BITBUCKET_WORKSPACES
    for workspace_id in workspaces_ids:
        
        for repository in bit.get_repositories_from_workspace(workspace_id):
            if REPO_SLUG and repository['slug'] != REPO_SLUG:
                continue
            for pr in bit.get_pull_requests(workspace_id, repository["uuid"], state="ALL", query=f"created_on>={DAYS_AGO.isoformat()}"):
                author_id = pr["author"]["account_id"]
                author_display_name = pr["author"]["display_name"]
                user_map_combined[author_id] = author_display_name
                pr_authors.add(author_id)

                comments = bit.get_pull_request_comments(workspace_id, repository["uuid"], pr["id"])
                tree = build_comment_tree(comments)

                unanswered_comments, user_map, participators, comment_makers = find_pull_request_metrics(comment_tree=tree, comment_url=pr['links']['html']['href'])
                user_map_combined.update(user_map)
                unanswered_comments_combined.update(unanswered_comments)
                for participator in participators:
                    participation.setdefault(participator, 0)
                    participation[participator] += 1
                comment_makers_combined.update(comment_makers)

    text = generate_report(unanswered_comments_combined, user_map_combined, participation, pr_authors, comment_makers_combined)

    if text:
        slack_client.chat_postMessage(channel=SLACK_CHANNEL, text=text, blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}])
    print("script ran successfully. output was: \n", text)


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
    
    if RUN_IMMEDIATELY:
        main(bit=bit, slack_client=slack_client)
    else:
        schedule = SafeScheduler(minutes_after_failure=5)
        schedule.every().day.at(WHEN_TO_RUN).do(main, bit=bit, slack_client=slack_client)

        print(f"current date: {datetime.now().strftime('%m/%d/%Y, %H:%M:%S')}")
        print("next job scheduled for:", schedule.next_run.strftime("%m/%d/%Y, %H:%M:%S"))

        while True:
            schedule.run_pending()
            time.sleep(1)

