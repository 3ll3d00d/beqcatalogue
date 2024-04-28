import os
from typing import List

from githubkit import GitHub, ActionAuthStrategy, Response
from githubkit.versions.v2022_11_28.models import Issue


class IssueManager:
    def __init__(self):
        self.github = GitHub(ActionAuthStrategy())

    def get_open_issues(self) -> List[Issue]:
        open_issues: Response[List[Issue]] = self.github.rest.issues.list_for_repo(owner='3ll3d00d', repo='beqcatalogue', state='open')
        if open_issues.status_code == 200:
            return open_issues.parsed_data
        else:
            raise Exception(str(open_issues))

    def close_issues(self, to_close: List[Issue]):
        for issue in to_close:
            self.github.rest.issues.update(owner='3ll3d00d', repo='beqcatalogue', issue_number=issue.number, state_reason='completed')
        pass


if __name__ == '__main__':
    issue_manager = IssueManager()
    issue_manager.get_open_issues()