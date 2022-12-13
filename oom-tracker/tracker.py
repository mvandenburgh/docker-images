from __future__ import annotations

import subprocess

from kubernetes import client, config
from kubernetes.client.models.v1_container_state import V1ContainerState
from kubernetes.client.models.v1_container_state_terminated import (
    V1ContainerStateTerminated,
)
from kubernetes.client.models.v1_container_status import V1ContainerStatus
from kubernetes.client.models.v1_object_meta import V1ObjectMeta
from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.client.models.v1_pod_status import V1PodStatus

try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

v1 = client.CoreV1Api()

top_records: dict[str, dict[str, str]] = {}

logged_oom_pods: set[str] = set()

while True:
    ret = v1.list_namespaced_pod("pipeline")
    pods: list[V1Pod] = ret.items

    pod_names = [pod.metadata.name for pod in pods]

    # Delete any stale entries
    for record in list(top_records.keys()):
        if record.split("/")[0] not in pod_names:
            del top_records[record]

    for pod in pods:
        pod_metadata: V1ObjectMeta = pod.metadata
        pod_status: V1PodStatus = pod.status
        container_statuses: list[
            V1ContainerStatus
        ] | None = pod_status.container_statuses

        if not container_statuses:
            continue

        # For each container in this pod, check if any have a status of OOMKilled
        for container_status in container_statuses:
            state: V1ContainerState = container_status.state
            terminated: V1ContainerStateTerminated | None = state.terminated
            # If this container has a status of OOMKilled, log it and print the last known memory
            # usage if it's available.
            if terminated and terminated.reason == "OOMKilled":
                if f"{pod_metadata.name}/{container_status.name}" in logged_oom_pods:
                    continue
                record = top_records.get(f"{pod_metadata.name}/{container_status.name}")
                if record:
                    print(
                        f"Container '{container_status.name}' on pod '{pod_metadata.name}' OOMKilled! {record}",
                        flush=True,
                    )
                    del top_records[f"{pod_metadata.name}/{container_status.name}"]
                else:
                    print(
                        f"Container '{container_status.name}' on pod '{pod_metadata.name}' OOMKilled, but no memory usage was recorded.",
                        flush=True,
                    )
                logged_oom_pods.add(f"{pod_metadata.name}/{container_status.name}")

        # Record memory usage of each container in this pod
        top_data = subprocess.run(
            [
                "kubectl",
                "-n",
                "pipeline",
                "top",
                "pod",
                pod_metadata.name,
                "--containers",
                "--no-headers",
            ],
            capture_output=True,
            text=True,
        ).stdout
        for line in top_data.splitlines():
            pod_name, container_name, duration, memory_usage = line.split()
            top_records[f"{pod_name}/{container_name}"] = {
                "duration": duration,
                "memory_usage": memory_usage,
            }
