#!/usr/bin/env bash

set -eu

printf '%s\n' "$*" >>"${FAKE_NOTIFIER_CALLS:?}"
