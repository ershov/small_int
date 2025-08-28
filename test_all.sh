#!/bin/bash

cd `dirname -- ${BASH_SOURCE[0]}` || exit $?

# Run all tests and save outputs
for f in small_*.py; do ./$f > output/${f%.py}.txt; done || exit $?

# Plot graphs
./make_graphs.sh
