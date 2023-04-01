#!/bin/bash
set -eu

cd "$1";
readarray -d '/' -t split_path <<<"$1/"; unset 'split_path[-1]'; declare -p split_path;
"$1/target/release/${split_path[-1]}";
