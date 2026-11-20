# syntax=docker/dockerfile:1
# Retain Apache's complete Kafka distribution and replace the complete musl JRE.
FROM apache/kafka:4.3.1@sha256:ccd1314e47ec76909e01f86308b4dcf2064f19f7c89759234322314b0e319e26

USER root
ADD --checksum=sha256:72835f41a468ae949fc058f8ec6a73d303ca3e5ea165621e08aacb36bb537bba https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13.1%2B2/OpenJDK21U-jre_x64_alpine-linux_hotspot_21.0.13.1_2.tar.gz /tmp/kafka-jre.tar.gz
COPY --chmod=755 install-jre.sh runtime-entrypoint.sh /usr/local/bin/
RUN apk upgrade --no-cache \
    && /usr/local/bin/install-jre.sh \
    && rm /usr/local/bin/install-jre.sh

ENV JAVA_VERSION=jdk-21.0.13.1+2
LABEL org.opencontainers.image.source="https://github.com/nanosamurai/nanosamurai" \
      org.opencontainers.image.title="Nanosamurai Kafka runtime" \
      org.opencontainers.image.description="Apache Kafka 4.3.1 with Eclipse Temurin 21.0.13.1+2"

USER appuser
ENTRYPOINT ["/usr/local/bin/runtime-entrypoint.sh"]
CMD ["/etc/kafka/docker/run"]
