#!/bin/bash
set -e
cd "$(dirname "$0")/../apps/desktop"

if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

echo "Starting frontend on http://localhost:1420"
npm run dev
