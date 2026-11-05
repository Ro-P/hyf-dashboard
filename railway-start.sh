#!/bin/sh
# Start script for Railway (and any other Docker host).
# If Google login settings are given as environment variables, write them
# to .streamlit/secrets.toml, where Streamlit's login expects them.
set -e
if [ -n "$AUTH_CLIENT_ID" ]; then
  mkdir -p .streamlit
  cat > .streamlit/secrets.toml <<TOML
[auth]
redirect_uri = "$AUTH_REDIRECT_URI"
cookie_secret = "$AUTH_COOKIE_SECRET"
client_id = "$AUTH_CLIENT_ID"
client_secret = "$AUTH_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
TOML
fi
exec streamlit run app.py --server.address=0.0.0.0 --server.port="${PORT:-8501}" --server.headless=true
