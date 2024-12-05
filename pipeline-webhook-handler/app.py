from datetime import datetime
from flask import Flask, request, jsonify
from opensearchpy import OpenSearch
import os


# Initialize Flask app
app = Flask(__name__)

# Configure OpenSearch connection
opensearch_client = OpenSearch(
    hosts=[os.environ["OPENSEARCH_HOST"]],
    http_auth=(os.environ["OPENSEARCH_USERNAME"], os.environ["OPENSEARCH_PASSWORD"]),
)


# Ensure the target index exists
def ensure_index_exists(index_name):
    if not opensearch_client.indices.exists(index=index_name):
        print(f"Creating index: {index_name}")
        opensearch_client.indices.create(index=index_name)
    else:
        print(f"Index already exists: {index_name}")


index_name = "gitlab-pipeline-webhooks"
ensure_index_exists(index_name)


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


@app.route("/", methods=["POST"])
def receive_webhook():
    # Parse incoming JSON payload
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "Invalid JSON payload"}), 400

    if payload.get("object_kind") != "pipeline":
        return jsonify({"error": "Invalid object_kind"}), 400
    if payload.get("object_attributes", {}).get("status") != "failed":
        return jsonify({"error": "Pipeline status is not failed"}), 400

    payload["@timestamp"] = datetime.now().isoformat()

    # Store the payload in OpenSearch
    response = opensearch_client.index(
        index="-".join([index_name, datetime.now().strftime("%Y%m%d")]), body=payload
    )

    # Return success response
    return (
        jsonify({"message": "Webhook received and stored", "id": response["_id"]}),
        200,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
