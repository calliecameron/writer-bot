FROM python:3.10-bookworm

RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY bin ./bin
COPY writer_bot ./writer_bot

ENTRYPOINT ["./main.py"]
