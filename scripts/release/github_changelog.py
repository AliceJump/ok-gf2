"""Generate release attribution from GitHub logins, never Git author names."""

import json
import os
import subprocess
import uuid
from pathlib import Path

MAINTENANCE_SUBJECTS = {"chore: ruff format", "update download stats"}


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, encoding="utf-8").stdout


def changelog(repository, start, end):
    # Resolve refs before constructing a range, and fail instead of publishing a partial log.
    end_sha = run("git", "rev-parse", "--verify", "--end-of-options", f"{end}^{{commit}}").strip()
    if start:
        start_sha = run("git", "rev-parse", "--verify", "--end-of-options", f"{start}^{{commit}}").strip()
        revision = f"{start_sha}..{end_sha}"
    else:
        revision = end_sha
    commits = run("git", "log", "--format=%H%x00%s", revision, "--")
    lines = []
    for line in commits.splitlines():
        sha, subject = line.split("\0", 1)
        if subject in MAINTENANCE_SUBJECTS:
            continue
        commit = json.loads(run("gh", "api", f"repos/{repository}/commits/{sha}"))
        # The nested commit.author.name is a Git display name and may be a real name.
        # Unlinked authors receive no attribution rather than a display-name fallback.
        login = (commit.get("author") or {}).get("login")
        attribution = f" (@{login})" if login else ""
        lines.append(f"* {subject}{attribution}")
    return "\n".join(lines)


def main():
    notes = changelog(os.environ["GITHUB_REPOSITORY"], os.environ["START_TAG"], os.environ["END_TAG"])
    delimiter = f"notes_{uuid.uuid4().hex}"
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"changes_with_asterisk<<{delimiter}\n{notes}\n{delimiter}\n")


if __name__ == "__main__":
    main()
