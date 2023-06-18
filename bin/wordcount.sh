#!/bin/bash

set -eu

function usage() {
    echo "Usage: $(basename "${0}") file type"
    exit 1
}

test -z "${1:-}" && usage
FILE="${1}"
test -z "${2:-}" && usage
TYPE="${2}"

if [ "${TYPE}" = 'text/plain' ]; then
    wc -w <"${FILE}"
elif [ "${TYPE}" = 'application/pdf' ]; then
    pdftotext "${FILE}" - | wc -w
else
    echo "Unknown type '${TYPE}'"
    exit 1
fi
