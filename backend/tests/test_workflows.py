# -*- coding: utf-8 -*-
"""Guards against a workflow that exists but does nothing.

An empty .github/workflows/*.yml is valid YAML with no jobs, so GitHub
accepts it and then fails every push with "No jobs were run". That is
exactly how this repo started emailing failure notices, so it is worth a
test rather than a comment.

Deliberately does not parse YAML, to avoid a dependency for one check.
"""

import glob
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOWS = os.path.join(REPO, ".github", "workflows")


def workflow_files():
    return sorted(
        glob.glob(os.path.join(WORKFLOWS, "*.yml"))
        + glob.glob(os.path.join(WORKFLOWS, "*.yaml"))
    )


def test_no_empty_workflow_files():
    for path in workflow_files():
        assert os.path.getsize(path) > 0, f"{os.path.basename(path)} is empty"


def test_every_workflow_declares_a_job():
    for path in workflow_files():
        with open(path, encoding="utf-8") as handle:
            body = handle.read()

        name = os.path.basename(path)
        assert "\njobs:" in body or body.startswith("jobs:"), f"{name} has no jobs"

        # A `jobs:` key with nothing under it fails the same way.
        after_jobs = body.split("jobs:", 1)[1]
        assert after_jobs.strip(), f"{name} declares jobs but defines none"
