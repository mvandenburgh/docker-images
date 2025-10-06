#!/usr/bin/env python3
"""
Fetch keep hashes from GitLab CI pipelines for pruning Spack buildcaches.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
import gitlab
import sys

try:
    import sentry_sdk
    sentry_sdk.init(
        traces_sample_rate=1.0,
    )
except Exception:
    print("Could not configure sentry.", file=sys.stderr)


def fetch_job_hashes(project, job_id, job_name):
    """Fetch hashes from a generate job's spack.lock artifact."""
    try:
        job = project.jobs.get(job_id, lazy=True)
        artifact_path = "jobs_scratch_dir/concrete_environment/spack.lock"
        artifact = job.artifact(artifact_path)
        lock = json.loads(artifact)
        hashes = list(lock["concrete_specs"].keys())
        print(f"  Found {len(hashes)} hashes in job {job_id}/{job_name}", file=sys.stderr)
        return hashes
    except gitlab.exceptions.GitlabHttpError as e:
        print(f"  Failed to fetch spack.lock for {job_id}/{job_name}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  Error processing job {job_id}/{job_name}: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Fetch keep hashes from GitLab pipelines"
    )
    parser.add_argument(
        "--gitlab-url",
        required=True,
        help="GitLab instance URL",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="GitLab project path (e.g., spack/spack)",
    )
    parser.add_argument(
        "--ref",
        default="develop",
        help="Git ref to fetch pipelines from",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=14,
        help="Number of days to look back for pipelines",
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output file for keep list",
    )

    args = parser.parse_args()

    # Connect to GitLab
    print(f"Connecting to {args.gitlab_url}...", file=sys.stderr)
    gl = gitlab.Gitlab(args.gitlab_url)
    project = gl.projects.get(args.project)

    # Calculate date range
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=args.since_days)

    print(f"Fetching pipelines from {args.ref} between {since.isoformat()} and {now.isoformat()}...", file=sys.stderr)

    # Collect hashes from all generate jobs
    all_hashes = set()
    pipeline_count = 0

    for pipeline in project.pipelines.list(
        iterator=True,
        updated_before=now,
        updated_after=since,
        ref=args.ref
    ):
        pipeline_count += 1
        print(f"Processing pipeline {pipeline.id}...", file=sys.stderr)

        for job in pipeline.jobs.list(iterator=True, scope="success"):
            if not job.stage == 'generate':
                continue

            hashes = fetch_job_hashes(project, job.id, job.name)
            all_hashes.update(hashes)

    print(f"\nProcessed {pipeline_count} pipelines", file=sys.stderr)
    print(f"Total unique hashes to keep: {len(all_hashes)}", file=sys.stderr)

    # Write keeplist file (one hash per line)
    with open(args.output, 'w') as f:
        for hash_val in sorted(all_hashes):
            f.write(f"{hash_val}\n")

    print(f"Keep list written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
