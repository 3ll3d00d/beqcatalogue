import glob
import os
from typing import List
from pathlib import Path

from githubkit import GitHub, ActionAuthStrategy, Response
from githubkit.versions.v2022_11_28.models import Issue


class IssueManager:
    def __init__(self):
        self.github = GitHub(ActionAuthStrategy())

    def get_open_issues(self) -> List[Issue]:
        resp: Response[List[Issue]] = self.github.rest.issues.list_for_repo(owner='3ll3d00d', repo='beqcatalogue',
                                                                            state='open')
        if resp.status_code == 200:
            return resp.parsed_data
        else:
            raise Exception(str(resp))

    def close_issue(self, author: str, to_close: Issue):
        print(f'Closing issue {to_close.number} for {author}')
        self.github.rest.issues.create_comment(owner='3ll3d00d', repo='beqcatalogue', issue_number=to_close.number,
                                               body=f'Fixed in {get_sha()}')
        self.github.rest.issues.update(owner='3ll3d00d', repo='beqcatalogue', issue_number=to_close.number,
                                       state='closed', state_reason='completed')

    def create_issue(self, author: str, errors: list[str]) -> bool:
        print(f'Creating new issue for {author}')
        resp = self.github.rest.issues.create(owner='3ll3d00d', repo='beqcatalogue',
                                              title=f'Bad input in author repository for {author}',
                                              body=f"Discovered in {get_sha()}\n\n{'\n'.join(errors)}",
                                              assignees=[author])
        if resp.status_code == 201:
            print(f'Created new issue {resp.parsed_data.number} for {author}')
            return True
        else:
            return False

    def update_issue_if_delta(self, author: str, errors: list[str], existing: Issue):
        if existing.body.endswith('\n\n' + '\n'.join(errors)):
            print(f'No update required for issue {existing.number} for {author}')
        else:
            print(f'Updating issue {existing.number} for {author}, errors have changed')
            self.github.rest.issues.update(owner='3ll3d00d', repo='beqcatalogue', issue_number=existing.number,
                                           body=f"Discovered in {get_sha()}\n\n{'\n'.join(errors)}")


def get_sha() -> str:
    return os.environ.get("COMMIT_SHA", "UNKNOWN SHA")


if __name__ == '__main__':
    issue_manager = IssueManager()
    open_issues = issue_manager.get_open_issues()
    issues_by_author = {}
    for issue in open_issues:
        import re

        m = re.match(r'^Bad input in author repository for (\w+)$', issue.title)
        if m:
            issues_by_author[m.group(1)] = issue
    errors_by_author = {}
    for errors_file_name in sorted(glob.glob(f"meta/*.errors")):
        author = Path(errors_file_name).stem
        with open(errors_file_name, 'r') as errors_file:
            errors_by_author[author] = [l.strip() for l in errors_file.readlines() if l.strip()]
            print(f'Found {len(errors_by_author[author])} errors for {author}')
    for author, errors in errors_by_author.items():
        issue = issues_by_author.get(author, None)
        if errors:
            if issue:
                issue_manager.update_issue_if_delta(author, errors, issue)
            else:
                issue_manager.create_issue(author, errors)
        else:
            if issue:
                issue_manager.close_issue(author, issue)
            else:
                print(f'No issue for {author} and no errors so nothing to do')
