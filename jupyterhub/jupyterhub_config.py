import os
from dockerspawner import SystemUserSpawner


# c.JupyterHub.base_url = ''

c.JupyterHub.authenticator_class = 'jupyterhub.auth.DummyAuthenticator'
# User containers will access hub by container name on the Docker network
c.JupyterHub.hub_ip = "jupyterhub"
c.JupyterHub.hub_port = 8080
c.DockerSpawner.default_url = "/lab"
c.Spawner.default_url = "/lab"

c.DockerSpawner.image = "live-notebook"
c.JupyterHub.spawner_class = "dockerspawner.DockerSpawner"
# Connect containers to this Docker network
network_name = os.environ["DOCKER_NETWORK_NAME"]
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.network_name = network_name
# Pass the network name as argument to spawned containers
c.DockerSpawner.extra_host_config = {"network_mode": network_name}
# c.DockerSpawner.disable_user_config = True
c.SystemUserSpawner.run_as_root = True
c.SystemUserSpawner.environment = {"CHOWN_HOME": "yes"}
c.JupyterHub.load_groups = {"teacher": ["teacher"]}
c.JupyterHub.services = [
    {
        "name": "Feedback",
        "url": "http://127.0.0.1:10102",
        "command": ["livefeedback-hub"],
        "environment": {"SERVICE_DB_URL": "sqlite:////srv/jupyterhub/data.db", "PYTHONUNBUFFERED": "1"},
        "oauth_no_confirm": True
    },
]
