FROM whisperx-worker
USER root
RUN pip install --no-cache-dir "psycopg[binary]==3.2.10" websockets==15.0.1
USER 10001
WORKDIR /probe
ENTRYPOINT ["python", "-u", "/probe/refinement/smoke.py"]
