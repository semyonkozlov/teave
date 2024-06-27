FROM python:3.11

ARG USERNAME=teave
RUN useradd -m ${USERNAME}
USER ${USERNAME}

WORKDIR /${USERNAME}
COPY infra/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .