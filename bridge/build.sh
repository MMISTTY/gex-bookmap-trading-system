#!/usr/bin/env bash
set -eu
: "${BOOKMAP_LIB_DIR:?Set BOOKMAP_LIB_DIR to your Bookmap SDK/lib directory containing API jars}"
cd "$(dirname "$0")"
mkdir -p build/classes
javac -cp "$BOOKMAP_LIB_DIR/*" -d build/classes src/main/java/io/gexbook/Capture.java
jar cf build/gexbook-capture.jar -C build/classes .
