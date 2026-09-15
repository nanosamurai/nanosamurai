FROM python:3.13-slim
WORKDIR /probe
RUN pip install --no-cache-dir confluent-kafka==2.12.0 protobuf==6.31.1 \
    "psycopg[binary]==3.2.10" websockets==15.0.1 boto3==1.40.0
COPY smoke.py migration.py /probe/
ENTRYPOINT ["python", "-u", "/probe/smoke.py"]
