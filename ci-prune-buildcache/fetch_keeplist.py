#!/usr/bin/env python3
"""
Fetch keep hashes from GitLab CI pipelines for pruning Spack buildcaches.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import gitlab
import sys

try:
    import sentry_sdk
    sentry_sdk.init(
        traces_sample_rate=1.0,
    )
except Exception:
    print("Could not configure sentry.", file=sys.stderr)


def fetch_job_hashes(project, job_id, job_name: str):
    """Fetch hashes from a generate job's spack.lock artifact."""
    try:
        job = project.jobs.get(job_id, lazy=True)
        stack_name = job_name.replace("-generate", "")
        artifact_path = f"jobs_scratch_dir/{stack_name}/concrete_environment/spack.lock"
        print(f"  Fetching artifact {artifact_path} from job {job_id}/{job_name}...", file=sys.stderr)
        artifact = job.artifact(artifact_path)
        lock = json.loads(artifact)
        hashes = list(lock["concrete_specs"].keys())
        print(f"  Found {len(hashes)} hashes in job {job_id}/{job_name}", file=sys.stderr)
        return hashes
    except (gitlab.exceptions.GitlabHttpError, gitlab.exceptions.GitlabGetError) as e:
        print(f"  Failed to fetch spack.lock for {job_id}/{job_name}: {e}", file=sys.stderr)
        return []


def process_pipeline(project, pipeline, max_workers=10):
    """Process all generate jobs in a pipeline in parallel."""
    print(f"Processing pipeline {pipeline.id}...", file=sys.stderr)

    # Collect all generate jobs
    generate_jobs = []
    for job in pipeline.jobs.list(iterator=True, scope="success"):
        if job.stage == 'generate':
            generate_jobs.append((job.id, job.name))

    # Fetch artifacts in parallel
    all_hashes = set()
    if generate_jobs:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_job = {
                executor.submit(fetch_job_hashes, project, job_id, job_name): (job_id, job_name)
                for job_id, job_name in generate_jobs
            }

            for future in as_completed(future_to_job):
                hashes = future.result()
                all_hashes.update(hashes)

    return all_hashes


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
    parser.add_argument(
        "--max-workers",
        type=int,
        default=10,
        help="Maximum number of parallel workers for fetching artifacts",
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

    # Collect all pipelines first
    pipelines = list(project.pipelines.list(
        iterator=True,
        updated_before=now,
        updated_after=since,
        ref=args.ref
    ))

    print(f"Found {len(pipelines)} pipelines to process", file=sys.stderr)

    # Process pipelines in parallel
    all_hashes = set()
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_pipeline = {
            executor.submit(process_pipeline, project, pipeline, args.max_workers): pipeline.id
            for pipeline in pipelines
        }

        for future in as_completed(future_to_pipeline):
            hashes = future.result()
            all_hashes.update(hashes)

    print(f"\nProcessed {len(pipelines)} pipelines", file=sys.stderr)
    print(f"Total unique hashes to keep: {len(all_hashes)}", file=sys.stderr)

    # Write keeplist file (one hash per line)
    with open(args.output, 'w') as f:
        for hash_val in sorted(all_hashes):
            f.write(f"{hash_val}\n")

    print(f"Keep list written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
