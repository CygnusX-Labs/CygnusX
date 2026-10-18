#!/bin/sh
# Run the export-create interception probe inside the browser container.
set -eu
cd /home/zj/zj_code_libarary/OmicHub
CREDS=$(docker exec cygnusx-ri095-acceptance-api-1 python3 -c "import json;d=json.load(open('/tmp/e2e-out/context.json'));print(d['owner'],d['owner_pw'],d['project'])")
U=$(echo "$CREDS" | cut -d' ' -f1)
P=$(echo "$CREDS" | cut -d' ' -f2)
PID=$(echo "$CREDS" | cut -d' ' -f3)
docker run --rm --user 10001:10001 \
  --security-opt seccomp=$PWD/deploy/acceptance/seccomp-browser.json \
  --cap-drop ALL --security-opt no-new-privileges:true --shm-size 1g \
  --network cygnusx-ri095-acceptance_isolated \
  -e UI_BASE=http://frontend:8080 -e RI095_USER="$U" -e RI095_PASS="$P" -e RI095_PROJECT="$PID" \
  -v $PWD/deploy/acceptance:/acceptance:ro \
  cygnusx-ri095-browser:v1.49.0 node /acceptance/probe-create.cjs
