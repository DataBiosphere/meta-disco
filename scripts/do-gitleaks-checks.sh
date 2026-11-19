#!/bin/bash

if ! gitleaks version 2>/dev/null | awk '
    !found && match($0, /[0-9]+\.[0-9]+/) {
        found = 1
        split(substr($0, RSTART, RLENGTH), v, ".")
        supported = v[1] > 8 || (v[1] == 8 && v[2] >= 20)
    }
    END { exit !supported }
'; then
    echo 'Gitleaks 8.20.0 or newer is required (brew install gitleaks).'
    exit 1
fi

gitleaks git --pre-commit --redact --staged --verbose
