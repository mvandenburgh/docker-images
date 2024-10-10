from kubernetes import client, config

config.load_config()
v1_client = client.CoreV1Api()


if __name__ == "__main__":
    metabase_pv = v1_client.read_persistent_volume("pvc-metabase")
    ebs_volume = metabase_pv.spec.csi.volume_handle
