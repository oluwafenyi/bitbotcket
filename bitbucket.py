from typing import Dict, Union
import json
import math

import requests
from requests import Session


class UnauthorizedBitbucketUserException(Exception):
    pass


def _generate_query_params(query_params: Dict[str, str]):
    params = [k + "=" + v for k, v in query_params.items()]
    return "?" + "&".join(params)


class Bitbucket:
    session: Session
    base_url: str = "https://api.bitbucket.org"

    def __init__(self, username: str, app_password: str):
        self.session = Session()
        self.session.auth = (username, app_password)
        self.session.headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _request(self, method, path, payload: dict = None) -> Union[requests.Response, None]:
        try:
            if payload:
                response = self.session.request(method, self.base_url + path, data=json.dumps(payload))
            else:
                response = self.session.request(method, self.base_url + path)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                raise UnauthorizedBitbucketUserException(f"User not authorized to access resource: {path}")
            raise
        return response

    def _request_iter(self, path: str, param: str = "values", batch: int = 50, query_params: dict = None, pages: int = 1E15):
        if query_params is not None:
            query_string = _generate_query_params({**query_params, "page": "1", "pagelen": str(batch)})
        else:
            query_string = _generate_query_params({"page": "1", "pagelen": str(batch)})
        response = self._request("GET", path + query_string)
        json_response = response.json()
        for resource in json_response[param]:
            yield resource

        size = json_response["size"]
        remaining_number_of_pages = min(pages, math.ceil(size / batch))
        for i in range(2, remaining_number_of_pages + 1):
            query_string = _generate_query_params({"page": str(i), "pagelen": str(batch)})
            response = self._request("GET", path + query_string)
            json_response = response.json()
            for resource in json_response[param]:
                yield resource

    def _get_resources(self, path: str, query_params: dict = None, batch: int = 50, pages: int = 1E15) -> list:
        resources = []
        for resource in self._request_iter(path, query_params=query_params, batch=batch, pages=pages):
            resources.append(resource)
        return resources

    def auth_test(self):
        return self.get_current_user_workspaces()

    def get_current_user_workspaces(self) -> list:
        return self._get_resources("/2.0/user/permissions/workspaces")

    def get_repositories_from_workspace(self, workspace_id: str) -> list:
        return self._get_resources(f"/2.0/repositories/{workspace_id}")

    def get_pull_requests(self, workspace_id: str, repository_slug: str, state: str = None, query: str = None, pages: int = 1) -> list:
        query_params = {}
        if state is not None:
            query_params = {"state": state}
        if query:
            query_params["q"] = query

        return self._get_resources(f"/2.0/repositories/{workspace_id}/{repository_slug}/pullrequests", query_params, batch=50, pages=pages)

    def get_pull_request_comments(self, workspace_id: str, repository_slug: str, pull_request_id: str) -> list:
        return self._get_resources(f"/2.0/repositories/{workspace_id}/{repository_slug}/pullrequests/{pull_request_id}/comments")
