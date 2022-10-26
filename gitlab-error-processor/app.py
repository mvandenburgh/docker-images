import json
from pathlib import Path
from fastapi import FastAPI, Request
from kubernetes import client, config
import yaml

config.load_incluster_config()

batch = client.BatchV1Api()

app = FastAPI()


@app.get("/")
async def grafana_endpoint():
    # TODO: This endpoint will return key/value pairs for prometheus to parse.
    return {"foo": "bar"}


@app.post("/")
async def gitlab_webhook_consumer(request: Request):
    # TODO: This endpoint will receive the gitlab webhook for failed jobs and
    # create a k8s job to parse the logs and upload them to opensearch.
    with open(Path(__file__).parent / 'job-template.yaml') as f:
        job_template = yaml.safe_load(f)

    job_input_data = await request.json()

    for container in job_template['spec']['template']['spec']['containers']:
        container.setdefault("env", []).extend(
            [
                dict(name="JOB_INPUT_DATA", value=json.dumps(job_input_data))
            ]
        )

    job_template['metadata']['name'] = "gitlab-error-processing-job"

    # Make sure to add labels to make finding the job that proccessed the error log
    # easier.
    job_template['metadata']['labels'] = {
        'spack.io/gitlab-job-id': '{{job_id}}',
        'spack.io/other-useful-annotation': '...'
    }

    # TODO:  make sure to add a namespace for running these jobs in
    batch.create_namespaced_job('gitlab-error-processor', job_template)
    return "ok"
