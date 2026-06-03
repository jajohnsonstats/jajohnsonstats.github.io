#!/bin/bash

# Resolve the directory of this script even when called from Windows
SCRIPT_DIR=$(dirname "$(realpath "$0")")

cd "$SCRIPT_DIR/.." || exit

git submodule update --remote --merge
