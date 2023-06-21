FROM python:3.10-bookworm

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY writer_bot ./writer_bot

ENTRYPOINT ["./main.py"]
