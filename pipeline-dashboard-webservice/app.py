from fastapi import FastAPI, Request

app = FastAPI()


@app.get("/")
async def grafana_endpoint():
    # TODO: This endpoint will return key/value pairs for prometheus to parse.
    return {"foo": "bar"}


@app.post("/")
async def gitlab_webhook_consumer(request: Request):
    # TODO: This endpoint will receive the gitlab webhook for failed jobs and
    # create a k8s job to parse the logs and upload them to opensearch.
    print(request.json)
    return "ok"
