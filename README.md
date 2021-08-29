# Live Feedback Extension for JupyterHub

This package provides a service extension for `JupyterHub` to collect notebooks from `JupyterLab`, check them using predefined `Otter-Grader` checks and saves the results in a database. The results can be used for real time feedback during study courses and to evaluate the knowledge anonymously.


## Requirements & Usage 

This tool makes use of the grading functionality of `Otter-Grader`. Therefore, access to a docker daemon is required. In case of hosting `JupyterHub` inside a docker container you need to pass the `docker.sock` to this container (e.g. using `-v /var/run/docker.sock:/var/run/docker.sock`). An example Dockerfile is provided in this repository installing all required packages for a common configuration containing OAuth authentication, DockerSpawner and the Live Feedback extension.

Furthermore, you must enable the service and provide a location for the (internal) database by setting the environment variable

```python
c.JupyterHub.services = [
    {
        "name": "Feedback",
        "url": "http://127.0.0.1:10102",
        "command": ["livefeedback-hub"],
        "environment": {"SERVICE_DB_URL": "sqlite:////srv/jupyterhub/data.db"},
        "oauth_no_confirm": True
     },
]
```
