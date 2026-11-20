#!/bin/sh
set -eu

# The pinned archive and Kafka platform manifest are both Linux amd64/musl.
[ "$(uname -m)" = x86_64 ]
[ "$JAVA_HOME" = /opt/java/openjdk ]
rm -rf /opt/java/openjdk
mkdir -p /opt/java/openjdk
tar -xzf /tmp/kafka-jre.tar.gz -C /opt/java/openjdk --strip-components=1 --no-same-owner
rm /tmp/kafka-jre.tar.gz
java -XshowSettings:properties -version 2>&1 | grep -F 'java.runtime.version = 21.0.13.1+2-LTS'

# Apache's two application CDS archives were built by the previous JVM.
# Keep the vendor launch script, removing only its two stale archive options.
[ "$(grep -c ' -XX:SharedArchiveFile=/opt/kafka/\(storage\|kafka\).jsa' /etc/kafka/docker/launch)" -eq 2 ]
sed -i 's@ -XX:SharedArchiveFile=/opt/kafka/storage.jsa@@; s@ -XX:SharedArchiveFile=/opt/kafka/kafka.jsa@@' /etc/kafka/docker/launch
! grep -q 'SharedArchiveFile=' /etc/kafka/docker/launch
rm /opt/kafka/storage.jsa /opt/kafka/kafka.jsa

# Preserve the platform's eMudhra hardening, including G1 if still bundled.
# https://ops.java/emudhra (custom application truststores are separate).
alias='cn_emsign_root_ca__g1,o_emudhra_technologies_limited,ou_emsign_pki,c_in [jdk]'
if keytool -list -v -cacerts -storepass changeit -alias "$alias" > /tmp/kafka-root.txt 2>/dev/null; then
    grep -F 'SHA256: 40:F6:AF:03:46:A9:9A:A1:CD:1D:55:5A:4E:9C:CE:62:C7:F9:63:46:03:EE:40:66:15:83:3D:C8:C8:D0:03:67' /tmp/kafka-root.txt
    keytool -delete -cacerts -storepass changeit -alias "$alias"
fi
keytool -list -v -cacerts -storepass changeit > /tmp/kafka-cacerts.txt
if grep -E 'Owner: CN=(emSign (ECC Root CA - G3|Root CA - G[12])|AAA Certificate Services),' /tmp/kafka-cacerts.txt; then
    echo 'Disallowed root remains in the default Java truststore' >&2
    exit 1
fi
rm /tmp/kafka-root.txt /tmp/kafka-cacerts.txt
