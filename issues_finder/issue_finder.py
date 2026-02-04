import requests
import sys
import time
import json
import os
from urllib.parse import urlparse
import re

MIN_FILES_CHANGED = 4
MIN_LINES_CHANGED = 150
MAX_LINES_CHANGED = 700
PER_PAGE = 50
MAX_PAGES = 10
OUTPUT_FILE = "issues.txt"
REQUEST_DELAY = 1
GITHUB_TOKEN = "" # NEVER HARDCODE TOKENS. Use an environment variable instead.
DEFAULT_REPO_URL = "https://github.com/ytdl-org/youtube-dl"
ISSUE_REF_REGEX = re.compile(r"(?:^|\s)#(\d+)\b")
ISSUE_CACHE = {}

# Run:
#   python issue_finder.py <repository_url> [--reset]
#   python issue_finder.py --reset

def get_github_token():
    return os.getenv("GITHUB_TOKEN", GITHUB_TOKEN)

def extract_repo_parts(repo_url):
    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError("Invalid GitHub repository URL. Example: https://github.com/pallets/flask")
    return parts[0], parts[1]

def load_scan_progress(repo_key):
    progress_file = "scan_progress.json"
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                progress = json.load(f)
                return progress.get(repo_key, {"scanned_pages": [], "last_cursor": None})
        except (json.JSONDecodeError, KeyError):
            pass
    return {"scanned_pages": [], "last_cursor": None}

def save_scan_progress(repo_key, scanned_pages, last_cursor):
    progress_file = "scan_progress.json"
    progress = {}
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                progress = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    progress[repo_key] = {"scanned_pages": scanned_pages, "last_cursor": last_cursor}
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)

def run_graphql_query(query, variables=None):
    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {get_github_token()}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "issue-finder-script",
    }
    res = requests.post(url, json={"query": query, "variables": variables or {}}, headers=headers)
    if res.status_code != 200:
        raise Exception(f"GraphQL query failed with status {res.status_code}: {res.text}")
    data = res.json()
    if "errors" in data:
        raise Exception(f"GraphQL query error: {data['errors']}")
    return data["data"]

def github_rest_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "issue-finder-script",
    }
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def fetch_issue_by_number(owner, repo, issue_number):
    cache_key = (owner, repo, issue_number)
    if cache_key in ISSUE_CACHE:
        return ISSUE_CACHE[cache_key]
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    res = requests.get(url, headers=github_rest_headers())
    if res.status_code != 200:
        ISSUE_CACHE[cache_key] = None
        return None
    data = res.json()
    if "pull_request" in data:
        ISSUE_CACHE[cache_key] = None
        return None
    issue = {
        "issue_title": data["title"],
        "issue_link": data["html_url"],
        "state": data["state"].upper(),
    }
    ISSUE_CACHE[cache_key] = issue
    return issue

def extract_issue_numbers(body_text):
    if not body_text:
        return set()
    return {int(match.group(1)) for match in ISSUE_REF_REGEX.finditer(body_text)}

def collect_open_issues(owner, repo, pr):
    open_issues = []
    seen = set()
    for issue in pr["closingIssuesReferences"]["nodes"]:
        if (issue.get("state") or "").upper() == "OPEN" and issue["url"] not in seen:
            open_issues.append({"issue_title": issue["title"], "issue_link": issue["url"]})
            seen.add(issue["url"])
    for number in extract_issue_numbers(pr.get("bodyText")):
        issue = fetch_issue_by_number(owner, repo, number)
        if issue and issue["state"] == "OPEN" and issue["issue_link"] not in seen:
            open_issues.append({"issue_title": issue["issue_title"], "issue_link": issue["issue_link"]})
            seen.add(issue["issue_link"])
    return open_issues

def fetch_and_process_prs(owner, repo):
    repo_key = f"{owner}/{repo}"
    progress = load_scan_progress(repo_key)
    scanned_pages = progress["scanned_pages"]
    after_cursor = progress["last_cursor"]
    total_prs_fetched = 0
    total_issues_saved = 0
    dynamic_max_pages = len(scanned_pages) + MAX_PAGES
    print(f"📊 Resuming scan from page {len(scanned_pages) + 1} (previously scanned: {len(scanned_pages)} pages)")
    print(f"📊 Will scan up to page {dynamic_max_pages} total")
    for page in range(1, dynamic_max_pages + 1):
        if page in scanned_pages:
            print(f"⏭️  Skipping page {page} (already scanned)")
            continue
        print(f"🔍 Fetching PRs page {page}...")
        query = """
        query($owner: String!, $repo: String!, $per_page: Int!, $after: String) {
          repository(owner: $owner, name: $repo) {
            pullRequests(first: $per_page, after: $after, states: MERGED, orderBy: {field: UPDATED_AT, direction: DESC}) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                number
                title
                bodyText
                additions
                deletions
                changedFiles
                closingIssuesReferences(first: 10) {
                  totalCount
                  nodes {
                    title
                    url
                    state
                  }
                }
              }
            }
          }
        }
        """
        variables = {"owner": owner, "repo": repo, "per_page": PER_PAGE, "after": after_cursor}
        data = run_graphql_query(query, variables)
        repo_data = data["repository"]
        if not repo_data or not repo_data["pullRequests"]:
            break
        pr_nodes = repo_data["pullRequests"]["nodes"]
        total_prs_fetched += len(pr_nodes)
        page_issues = filter_prs(owner, repo, pr_nodes)
        if page_issues:
            save_to_txt(page_issues)
            total_issues_saved += len(page_issues)
        scanned_pages.append(page)
        page_info = repo_data["pullRequests"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        after_cursor = page_info["endCursor"]
        save_scan_progress(repo_key, scanned_pages, after_cursor)
        time.sleep(REQUEST_DELAY)
    print(f"\n📊 Summary: Fetched {total_prs_fetched} PRs, saved {total_issues_saved} issues")
    return total_prs_fetched, total_issues_saved

def filter_prs(owner, repo, prs):
    results = []
    for pr in prs:
        total_lines = pr["additions"] + pr["deletions"]
        is_docs_pr = pr["title"].lower().startswith("docs:")
        if (
            pr["changedFiles"] < MIN_FILES_CHANGED
            or total_lines < MIN_LINES_CHANGED
            or total_lines > MAX_LINES_CHANGED
            or is_docs_pr
        ):
            continue
        open_issues = collect_open_issues(owner, repo, pr)
        if len(open_issues) != 1:
            continue
        issue = open_issues[0]
        results.append(issue)
        print(f"✅ PR #{pr['number']} ({pr['changedFiles']} files, {total_lines} lines, 1 open issue)")
    return results

def save_to_txt(issues):
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for issue in issues:
            f.write(f"{issue['issue_link']} - {issue['issue_title']}\n")
    if issues:
        print(f"\n🗒️ Added {len(issues)} issues to {OUTPUT_FILE}")
    else:
        print(f"\n🗒️ No new issues found to add to {OUTPUT_FILE}")

def reset_progress(repo_key):
    progress_file = "scan_progress.json"
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                progress = json.load(f)
            if repo_key in progress:
                del progress[repo_key]
                with open(progress_file, "w") as f:
                    json.dump(progress, f, indent=2)
                print(f"🔄 Reset progress for {repo_key}")
        except (json.JSONDecodeError, FileNotFoundError):
            pass

def main():
    args = sys.argv[1:]
    reset_flag = "--reset" in args
    repo_url = next((arg for arg in args if not arg.startswith("--")), None)
    if not repo_url:
        if not DEFAULT_REPO_URL:
            print("Usage: python issue_finder.py <repository_url> [--reset]")
            print("Example: python issue_finder.py https://github.com/pallets/flask")
            print("         python issue_finder.py https://github.com/pallets/flask --reset")
            sys.exit(1)
        repo_url = DEFAULT_REPO_URL
        print(f"ℹ️  No repository URL provided, defaulting to {repo_url}")
    owner, repo = extract_repo_parts(repo_url)
    repo_key = f"{owner}/{repo}"
    if reset_flag:
        reset_progress(repo_key)
    print(f"🗂️ Searching in repository: {owner}/{repo}")
    fetch_and_process_prs(owner, repo)

if __name__ == "__main__":
    main()