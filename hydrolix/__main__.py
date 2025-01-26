import pulumi
import pulumi_kubernetes as kubernetes
from pulumi_kubernetes.yaml import ConfigFile


# Set of configs with default values
config = pulumi.Config()

# Values come from cluster deployment project if they are unset in config
# TODO: Set your stack FQDN
parent_pulumi_stack = config.get("parent_stack", "asaraseka/asaraseka-hydro/dev")
stack_ref = pulumi.StackReference(parent_pulumi_stack)

hydrolix_db_bucket_region = config.get("bucket_region", stack_ref.get_output("bucket_region"))
hydrolix_db_bucket_url = config.get("bucket_url", stack_ref.get_output("bucket_name"))
service_account_name = config.get("service_account", stack_ref.get_output("service_account"))

# Values come from config with default values
ns_name = config.get("namespace", "hydrolix")

hydrolix_operator_yaml = config.get("operator_yaml_path", "./files/operator.yaml")
hydrolix_cluster_yaml = config.get("cluster_yaml_path", "./files/hydrolixcluster-gcp.yaml")
hydrolix_cluster_name = config.get("cluster_name", "hdx")
hydrolix_admin_email = config.get("admin_email", "some_email@gmail.com")
hydrolix_url = config.get("url", "https://hdx.something.name")
hydroilx_ip_allowlist = ["0.0.0.0/0"]


namespace = kubernetes.core.v1.Namespace(ns_name, metadata={"name": ns_name})

# Transformations for yaml files to use configurable values
def set_hydrolix_custom_values(obj, opts):
    if obj["kind"] != "CustomResourceDefinition":
        try:
            # Set desired namespace for all resources except operator itself
            obj["metadata"]["namespace"] = ns_name
            # For roles binding namespace is used also in scopes
            if obj["kind"] == "ClusterRoleBinding" or obj["kind"] == "RoleBinding":
                for subject in obj["subjects"]:
                    try:
                        subject["namespace"] = ns_name
                    except KeyError:
                        pass
            # For service account need to set gke service account
            if obj["kind"] == "ServiceAccount":
                try:
                    obj["metadata"]["annotations"]["iam.gke.io/gcp-service-account"] = service_account_name
                except KeyError:
                    pass
            if obj["kind"] == "HydrolixCluster":
                # Set required custom values for Hydrolix Cluster yaml
                try:
                    obj["spec"]["kubernetes_namespace"] = ns_name
                    obj["spec"]["admin_email"] = hydrolix_admin_email
                    obj["spec"]["db_bucket_region"] = hydrolix_db_bucket_region
                    obj["spec"]["db_bucket_url"] = hydrolix_db_bucket_url
                    obj["spec"]["hydrolix_name"] = hydrolix_cluster_name
                    obj["spec"]["hydrolix_url"] = hydrolix_url
                    obj["spec"]["ip_allowlist"] = hydroilx_ip_allowlist
                except KeyError:
                    pass
        except KeyError:
            pass


hydrolix_operator = ConfigFile(
    "hydrolix_operator",
    file=hydrolix_operator_yaml,
    transformations=[set_hydrolix_custom_values],
    opts=pulumi.ResourceOptions(parent=namespace)
)

hydrolix_cluster = ConfigFile(
    name="hydrolix_cluster",
    file=hydrolix_cluster_yaml,
    transformations=[set_hydrolix_custom_values],
    opts=pulumi.ResourceOptions(parent=hydrolix_operator)
)
