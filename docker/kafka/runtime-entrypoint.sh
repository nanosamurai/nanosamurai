#!/bin/sh
set -eu

# Retain caller options and apply the defense-in-depth setting to every JVM,
# including the one-shot topic tools. Preserve Temurin's CA entrypoint.
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:+$JAVA_TOOL_OPTIONS }-XX:-UseBASE64Intrinsics"
exec /__cacert_entrypoint.sh "$@"
