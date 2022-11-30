from __future__ import annotations

import json
import logging
import os
import re
import tarfile
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

import boto3
import gitlab
import pyjson5
import requests
from botocore import UNSIGNED
from botocore.client import Config
from kubernetes import client, config

# Authenticate the boto3 client with AWS.
# Since the spack build cache is a public S3 bucket, we don't need credentials
s3 = boto3.client(
    "s3",
    config=Config(retries={"mode": "adaptive"}, signature_version=UNSIGNED),
    region_name="us-east-1",
)

logging.basicConfig(level=logging.ERROR)  # Only log ERROR messages

BUCKET = "spack-binaries"
PREFIX = "develop/build_cache"

OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_USERNAME = os.environ["OPENSEARCH_USERNAME"]
OPENSEARCH_PASSWORD = os.environ["OPENSEARCH_PASSWORD"]

METABASE_USERNAME = os.environ["METABASE_USERNAME"]
METABASE_PASSWORD = os.environ["METABASE_PASSWORD"]

TODAY = datetime.today()

gl = gitlab.Gitlab("https://gitlab.spack.io", os.environ["GITLAB_TOKEN"])

# Get client ca from a k8s secret
config.load_incluster_config()
v1 = client.CoreV1Api()
client_ca = v1.read_namespaced_secret("client-ca", "ingress-nginx").to_dict()

print(client_ca)

metabase_session = requests.Session()

# Get a session token from the metabase API
with (
    NamedTemporaryFile("r+") as crt,
    NamedTemporaryFile("r+") as key,
):
    crt.write(client_ca["data"]["ca.crt"])
    key.write(client_ca["data"]["ca.key"])
    print(client_ca["data"]["ca.crt"])
    print(client_ca["data"]["ca.key"])
    print('test')
    print(Path(crt.name).read_text())
    print(Path(key.name).read_text())

    res = metabase_session.post(
        "https://metabase.spack.io/api/session",
        data=json.dumps(
            {
                "username": METABASE_USERNAME,
                "password": METABASE_PASSWORD,
            }
        ),
        headers={"Content-Type": "application/json"},
        cert=(
            crt.name,
            key.name,
        ),
    )

session_id: str = res.json()["id"]


def get_gitlab_build_job_metadata(build_hash: str) -> dict:
    """
    Get metadata from the gitlab job that performed this build.

    Searches metabase for the gitlab job with the given build hash,
    then uses the resulting job ID to get the job's metadata from
    the gitlab API.
    """
    shortened_build_hash = build_hash[:7]

    with (
        NamedTemporaryFile("r+") as crt,
        NamedTemporaryFile("r+") as key,
    ):
        crt.write(client_ca["data"]["ca.crt"])
        key.write(client_ca["data"]["ca.key"])

        res = requests.post(
            "https://metabase.spack.io/api/dataset",
            data=json.dumps(
                {
                    "type": "query",
                    "query": {
                        "source-table": 893,
                        "filter": [
                            "contains",
                            ["field", 10263, None],
                            f"/{shortened_build_hash}",
                            {"case-sensitive": False},
                        ],
                    },
                    "database": 3,
                    "parameters": [],
                }
            ),
            headers={
                "Content-Type": "application/json",
                "X-Metabase-Session": session_id,
            },
            cert=(
                crt.name,
                key.name,
            ),
        )

    rows: list[list[str]] = res.json()["data"]["rows"]

    # Get most recent successful build
    row = [r for r in rows if r[0] == "success"][0]

    gitlab_job_id = int(row[-2])

    project = gl.projects.get(2)
    job = project.jobs.get(gitlab_job_id)

    return json.loads(job.to_json())


def post_logs(log_data):
    """Post the given JSON log data to OpenSearch."""

    def _convert_booleans_to_strings(obj):
        if isinstance(obj, bool):
            return str(obj).lower()
        if isinstance(obj, (list, tuple)):
            return [_convert_booleans_to_strings(item) for item in obj]
        if isinstance(obj, dict):
            return {
                key: _convert_booleans_to_strings(value) for key, value in obj.items()
            }
        return obj

    res = requests.post(
        f"{OPENSEARCH_ENDPOINT}/pipeline-logs-{TODAY.strftime('%Y.%m.%d')}/_doc",
        data=json.dumps(_convert_booleans_to_strings(log_data)),
        headers={"Content-Type": "application/json"},
        auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
    )
    res.raise_for_status()


def upload_to_opensearch(
    build_hash: str,
    spec_json: dict,
    install_times_json: dict,
):
    """
    Given a spec.json, install_times.json, and spack-build-out files, package them all
    into a single JSON document and POSTs them to the OpenSearch API.
    """
    document: dict[str, Any] = {}

    document["hash"] = build_hash
    document["spec"] = spec_json["spec"]
    document["install_times"] = install_times_json
    document["gitlab_job_metadata"] = get_gitlab_build_job_metadata(build_hash)

    post_logs(document)


def create_opensearch_index():
    """
    Create an opensearch index for the current date.

    This operation is idempotent; if an index already exists for the current date, the server will
    not create a new one.
    """
    index_name = f"pipeline-logs-{TODAY.strftime('%Y.%m.%d')}"
    with open(Path(__file__).parent / "pipeline_logs_mapping.json5") as fd:
        index_mappings = pyjson5.load(fd)
    res = requests.put(
        f"{OPENSEARCH_ENDPOINT}/{index_name}",
        data=json.dumps(index_mappings),
        headers={"Content-Type": "application/json"},
        auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
    )
    if res.status_code >= 400:
        logging.error(
            f'Failed to create opensearch index "{index_name}", '
            f"server responded with status {res.status_code}"
        )
        try:
            logging.error(res.json())
        except json.JSONDecodeError:
            logging.error(res.text)


def fetch_and_upload_tarball(spec_json_sig_key: str):
    logging.info(f'Fetching and uploading "{spec_json_sig_key}"...')

    # Extract metadata from *.spec.json.sig filename
    (os_arch, compiler, package, build_hash) = re.findall(
        rf"{PREFIX}/(.+)-(.+-[\d+\.]+)-(.+)-(.+).spec.json.sig",
        spec_json_sig_key,
    )[0]

    # Check if a document with this hash already exists, and if so don't upload it.
    res = requests.get(
        f"{OPENSEARCH_ENDPOINT}/pipeline-logs*/_search",
        data=json.dumps({"query": {"match": {"hash": build_hash}}}),
        headers={"Content-Type": "application/json"},
        auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
    )
    res.raise_for_status()

    if res.json()["hits"]["total"]["value"] > 0:
        logging.info(
            f"Skipping upload of record with build hash {build_hash} - already exists."
        )
        return

    binary_prefix = f"{PREFIX}/{os_arch}/{compiler}/{package}"
    file_path = f"{binary_prefix}/{os_arch}-{compiler}-{package}-{build_hash}.spack"

    try:
        # Download the tarball, extract it to a temp directory, parse the build logs we're
        # interested in, and POST them to the OpenSearch cluster.
        with NamedTemporaryFile("rb+") as f:
            s3.download_fileobj(BUCKET, file_path, f)
            with tarfile.open(
                f.name, mode="r:gz"
            ) as tar, TemporaryDirectory() as temp_dir:
                tar.extract(f"{package}-{build_hash}/.spack/spec.json", path=temp_dir)
                tar.extract(
                    f"{package}-{build_hash}/.spack/install_times.json", path=temp_dir
                )

                spec_json = json.loads(
                    (
                        Path(temp_dir)
                        / f"{package}-{build_hash}"
                        / ".spack"
                        / "spec.json"
                    ).read_text()
                )
                install_times = json.loads(
                    (
                        Path(temp_dir)
                        / f"{package}-{build_hash}"
                        / ".spack"
                        / "install_times.json"
                    ).read_text()
                )

                upload_to_opensearch(build_hash, spec_json, install_times)
    except Exception as e:
        # Catch all exceptions and log error instead of crashing script
        logging.error(f'Error occurred while processing Key "{spec_json_sig_key}"')
        logging.error(f"Tarball S3 Key = {file_path}")
        logging.error(str(e))
        if isinstance(e, requests.HTTPError):
            try:
                logging.error(str(e.response.json()) + "\n\n")
            except json.JSONDecodeError:
                logging.error(str(e.response.content) + "\n\n")
        return


def main():
    """Iterate over the entire S3 bucket and send any new build logs to OpenSearch."""
    create_opensearch_index()

    all_pages = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        contents = [
            key["Key"]
            for key in page["Contents"]
            if key["Key"].endswith(".spec.json.sig")
        ]
        all_pages.extend(contents)

    with Pool(processes=os.cpu_count()) as pool:
        pool.map(fetch_and_upload_tarball, all_pages)
        pool.close()
        pool.join()


if __name__ == "__main__":
    main()
