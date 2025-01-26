"""A Google Cloud Python Pulumi program"""

import pulumi
import pulumi_gcp as gcp
from pulumi_gcp import storage

provider_cfg = pulumi.Config("gcp")
gcp_project = provider_cfg.require("project")
gcp_region = provider_cfg.get("region", "us-east1")
gcp_zone = provider_cfg.get("zone", "us-east1-b")

# Set of configs with default values
config = pulumi.Config()
nodes_per_zone = config.get_int("nodesPerZone", 1)
nodes_machine_type = config.get("machineType", "e2-standard-8")
gke_cluster_name = config.get("kubernetes_cluster", "gke-cluster")
bucket_name = config.get("bucket", "asaraseka-hydrolix")
bucket_region = config.get("bucket_region", gcp_region)
kubernetes_namespace_name = config.get("namespace", "hydrolix")
network_name = config.get("network", "gke-network")

# Create subnet for GKE
gke_network = gcp.compute.Network(
    network_name,
    auto_create_subnetworks=False,
    description="A virtual network for your GKE cluster(s)"
)

# Create a subnet in the new network
gke_subnet = gcp.compute.Subnetwork(
    "gke-subnet",
    ip_cidr_range="10.128.0.0/12",
    network=gke_network.id,
    region=gcp_region,
    opts=pulumi.ResourceOptions(depends_on=[gke_network])
)

# Create a GCP service account for the GKE cluster
# TODO: Add to StorageAdmin role fot bucket
gke_nodepool_sa = gcp.serviceaccount.Account(
    "gke-nodepool-sa",
    account_id="gke-nodepool-sa",
    display_name="Node Pool Service Account",
    # project=gcp_project
)

# Create a GCP resource (Storage Bucket)
bucket = storage.Bucket(
    bucket_name,
    location=bucket_region,
    storage_class="REGIONAL",
    name=bucket_name,
    force_destroy=True,
    opts=pulumi.ResourceOptions(depends_on=[gke_nodepool_sa])
)


# Provide access to GKE service account
bucket_acl_full = gcp.storage.BucketAccessControl(
    "allow_gke_full",
    bucket=bucket.name,
    role="OWNER",
    entity=gke_nodepool_sa.email.apply(lambda email: f"user-{email}"),
)

# Create a cluster in the new network and subnet
gke_cluster = gcp.container.Cluster(
    gke_cluster_name,
    # remove_default_node_pool=True,
    description="A GKE cluster",
    location=gcp_zone,
    initial_node_count=3,
    master_authorized_networks_config={
        "cidr_blocks": [
          {"cidr_block": "83.10.32.65/32", "display_name": "Home"}
        ]
    },
    monitoring_config={
        "enable_components": [],
        "managed_prometheus": {
            "enabled": False,
        },
    },
    addons_config={
        "gce_persistent_disk_csi_driver_config": {
            "enabled": True,
        }
    },
    logging_config={
        "enable_components": [],
    },
    node_config=gcp.container.ClusterNodeConfigArgs(
        machine_type=nodes_machine_type,
        disk_type="pd-standard",
        disk_size_gb=300,
        oauth_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        labels={
            "env": "dev",
        },
        tags=["gke-node"],
        service_account=gke_nodepool_sa.email,
    ),
    network=gke_network.name,
    subnetwork=gke_subnet.name,
    deletion_protection=False,
    opts=pulumi.ResourceOptions(depends_on=[gke_nodepool_sa, gke_network, gke_subnet])
)

# Build a Kubeconfig to access the cluster
cluster_kubeconfig = pulumi.Output.all(
    gke_cluster.master_auth.cluster_ca_certificate,
    gke_cluster.endpoint,
    gke_cluster.name).apply(lambda l:
    f"""apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {l[0]}
    server: https://{l[1]}
  name: {l[2]}
contexts:
- context:
    cluster: {l[2]}
    user: {l[2]}
  name: {l[2]}
current-context: {l[2]}
kind: Config
preferences: {{}}
users:
- name: {l[2]}
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: gke-gcloud-auth-plugin
      installHint: Install gke-gcloud-auth-plugin for use with kubectl by following
        https://cloud.google.com/blog/products/containers-kubernetes/kubectl-auth-changes-in-gke
      provideClusterInfo: true
""")

# Export the DNS name of the bucket
pulumi.export('stack_fqdn', f'{pulumi.get_organization()}/{pulumi.get_project()}/{pulumi.get_stack()}')
pulumi.export('bucket_name', bucket.url)
pulumi.export('bucket_region', bucket_region)
pulumi.export("network_name", gke_network.name)
pulumi.export("network_id", gke_network.id)
pulumi.export("cluster_name", gke_cluster.name)
pulumi.export("service_account", gke_nodepool_sa.email)
pulumi.export("cluster_id", gke_cluster.id)
pulumi.export("kubeconfig", cluster_kubeconfig)
