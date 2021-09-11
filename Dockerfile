FROM jupyterhub/jupyterhub

# Install dockerspawner, oauth and live feedback
RUN pip install --no-cache-dir \
        dockerspawner otter-grader
ARG DOCKER_VERSION=20.10.7
RUN cd /tmp && \
    curl -sSL -O https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz && \
    tar zxf docker-${DOCKER_VERSION}.tgz && \
    mv ./docker/docker /usr/local/bin && \
    chmod +x /usr/local/bin/docker && rm -rf /tmp/*
COPY --from=docker/buildx-bin /buildx /usr/libexec/docker/cli-plugins/docker-buildx
COPY . /tmp/extension
RUN cd /tmp/extension && pip install .

