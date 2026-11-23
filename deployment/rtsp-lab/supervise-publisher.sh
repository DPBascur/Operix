#!/bin/sh
# Keep the service idle until the trusted backend grants a short lease.
set -eu
case "$CAMERA_PATH" in lab-cam-01|lab-cam-02) ;; *) exit 1;; esac
lease="/lab-control/$CAMERA_PATH.lease"
child=
current=
stop() {
    if [ -n "$child" ]; then
        kill -TERM "$child" 2>/dev/null || true
        wait "$child" || true
    fi
    child=
    current=
}
trap 'stop; exit 0' INT TERM

while :; do
    desired=
    if [ -r "$lease" ]; then
        modified=$(stat -c %Y "$lease" 2>/dev/null || printf 0)
        age=$(($(date +%s) - modified))
        if [ "$age" -ge 0 ] && [ "$age" -lt 12 ]; then
            desired=$(cat "$lease" 2>/dev/null || true)
        fi
    fi
    if [ "$desired" != "$current" ]; then
        stop
    fi
    if [ -n "$child" ] && ! kill -0 "$child" 2>/dev/null; then
        wait "$child" || true
        child=
        current=
        sleep 2
        continue
    fi
    if [ -n "$desired" ] && [ -z "$child" ]; then
        IFS=' ' read -r filename digest extra <<EOF
$desired
EOF
        if [ -n "$filename" ] && [ -n "$digest" ] && [ -z "$extra" ]; then
            VIDEO_FILE="$filename" VIDEO_SHA256="$digest" /bin/sh /lab/publish.sh &
            child=$!
            current=$desired
        fi
    fi
    sleep 1
done
