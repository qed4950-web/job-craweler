#!/bin/bash

echo "Starting Cloudflare Tunnel to http://localhost:8000 ..."
cloudflared tunnel --url http://localhost:8000
