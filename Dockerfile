# Our Airflow image = the official Airflow 3.3.2 image + the Python packages our pipeline needs.
FROM apache/airflow:3.3.2

# Install our packages. Pinning apache-airflow in the same command stops pip from
# upgrading or downgrading Airflow by accident while it installs our requirements.
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==3.3.2" -r /requirements.txt
.dockerignore
