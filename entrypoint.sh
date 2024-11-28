#!/bin/bash

# Exit on error
set -e

echo "Starting Gunicorn server..."
exec waitress-serve --listen=0.0.0.0:8000 gamedata_api:app