#!/bin/bash

# Exit on error
set -e

echo "Starting Gunicorn server..."
exec waitress-serve --listen=0.0.0.0:8000 --url-scheme=https --trusted-proxy='*' --trusted-proxy-headers='x-forwarded-for,x-forwarded-proto,x-forwarded-host' gamedata_api:app