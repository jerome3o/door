#!/bin/bash

lenv () 
{ 
    filename=${1:-.env}
    if [ -f "$filename" ]; then
        set -a
        source "$filename"
        set +a
        echo "Environment variables loaded from $filename"
    else
        echo "File not found: $filename"
    fi
}

cd /home/jerome/source/well_actually/ || exit 1
lenv
exec ./venv/bin/uvicorn main:app --host 127.0.0.1
