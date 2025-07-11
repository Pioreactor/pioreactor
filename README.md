<img src="https://user-images.githubusercontent.com/884032/101398418-08e1c700-389c-11eb-8cf2-592c20383a19.png" width="250">
<br />


[![CI](https://github.com/Pioreactor/pioreactor/actions/workflows/ci.yaml/badge.svg)](https://github.com/Pioreactor/pioreactor/actions/workflows/ci.yaml)

The Pioreactor is a *mostly* open source, affordable, and extensible bioreactor platform. The goal is to enable biologists, educators, DIYers, biohackers, and enthusiasts to be able to reliably control and study microorganisms.

We hope to empower the next generation of builders, similar to the Raspberry Pi's influence on our imagination (in fact, at the core of our hardware _is_ a Raspberry Pi). However, the builders in mind are those who are looking to use biology, or computer science, or both, to achieve their goals. For research, the affordable price point enables fleets of Pioreactors to study large experiment spaces. For educators and students, the Pioreactor is a learning tool to study a wide variety of microbiology, electrical engineering, and computer science principles. For enthusiasts, the control and extensibility of the Pioreactor gives them a platform to build their next project on-top of.



### Where can I get one?

Purchase [on our website](https://pioreactor.com/).

### Documentation

All the documentation is [available on our docs site](https://docs.pioreactor.com/).
## Dockerized development (experimental)

You can spin up the entire development stack—including the Huey worker (using SQLite broker), the Flask API, and the React frontend—using Docker Compose.

Before first run, create a local cache directory for Huey:
```bash
mkdir -p pioreactor_cache
```
Then start everything:

```bash
docker-compose up --build
```

This will start:

- **huey**: Huey consumer running background Pioreactor tasks (SQLite broker at `pioreactor_cache/huey.db`).
- **web**: Flask API server (listening on port 4999).
- **frontend**: React development server (listening on port 3000).

Each service is defined by its own Dockerfile:

* `web/Dockerfile`: builds and runs both the Huey worker and the Flask API.
* `frontend/Dockerfile`: builds and runs the React UI.

A top-level `docker-compose.yml` brings the services together and mounts the code for live development.
Make sure you have Docker and Docker Compose installed before trying this out.
