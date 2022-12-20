from datetime import datetime
import os

from opensearch_dsl import Date, Document, connections


class JobPayload(Document):
    timestamp = Date()

    class Index:
        name = "gitlab-job-failures-*"

    def save(self, **kwargs):
        # assign now if no timestamp given
        if not self.timestamp:
            self.timestamp = datetime.now()

        # override the index to go to the proper timeslot
        kwargs["index"] = self.timestamp.strftime("gitlab-job-failures-%Y%m%d")
        return super().save(**kwargs)


OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_USERNAME = os.environ["OPENSEARCH_USERNAME"]
OPENSEARCH_PASSWORD = os.environ["OPENSEARCH_PASSWORD"]

connections.create_connection(
    hosts=[OPENSEARCH_ENDPOINT],
    http_auth=(
        OPENSEARCH_USERNAME,
        OPENSEARCH_PASSWORD,
    ),
)

print('Begin migration...')
results = JobPayload.search()
for job in results.scan():
    job_input_data = job.to_dict()
    doc = JobPayload.get(id=job.meta["id"], index=job.meta["index"])

    build_id = job_input_data["build_id"]

    job_link = f"https://gitlab.spack.io/spack/spack/-/jobs/{build_id}"
    job_trace_link = f"https://gitlab.spack.io/api/v4/projects/2/jobs/{build_id}/trace"

    try:
        doc = JobPayload.get(id=job.meta["id"], index=job.meta["index"])
        doc.gitlab_job_url = job_link
        doc.gitlab_job_trace_url = job_trace_link

        doc.save()
    except:
        print(job_input_data)
        continue
