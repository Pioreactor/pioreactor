# Dockerfile for Pioreactor Flask API (web)
FROM python:3.11-slim

WORKDIR /app

# install make for running Makefile targets
RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

# copy requirements and install runtime dependencies
COPY requirements/requirements.txt requirements/
RUN pip install --no-cache-dir -r requirements/requirements.txt

# copy project source (core logic & API)
COPY core/ core/
COPY web/ web/
COPY Makefile .

# build virtual environment and install project dependencies
RUN make install

# start Flask development server
CMD ["make", "web-dev"]
