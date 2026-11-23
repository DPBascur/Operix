#!/bin/sh
# The backend owns commands. This publisher can acknowledge only its own slot.
set -eu
case "$CAMERA_PATH" in lab-cam-01|lab-cam-02) ;; *) exit 1;; esac
lease="/lab-control/$CAMERA_PATH.lease"
ack=/lab-ack/status
progress=/lab-ack/progress
child=
current=
token=
state=

report() {
    state=$1
    printf '%s %s\n' "$token" "$state" > "$ack.tmp"
    mv -f "$ack.tmp" "$ack"
}

stop() {
    if [ -n "$child" ]; then
        kill -TERM "$child" 2>/dev/null || true
        wait "$child" || true
        child=
        report expired
    fi
}
trap 'stop; exit 0' INT TERM

valid_token() {
    case "$1" in ""|*[!0-9a-f]*) return 1;; esac
    [ "${#1}" -eq 32 ]
}

# A restarted supervisor must not replay an outstanding attempt.
if [ -r "$ack" ]; then
    IFS=' ' read -r token state extra < "$ack" || true
    if valid_token "$token"; then
        case "$state" in launching|playing) report expired;; esac
    fi
fi

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
        current=$desired
        if [ -n "$desired" ]; then
            IFS=' ' read -r requested command filename digest extra <<EOF
$desired
EOF
            if valid_token "$requested"; then
                case "$command" in
                    idle)
                        if [ -z "$filename" ]; then
                            token=$requested
                            report idle
                        fi
                        ;;
                    play)
                        # Accept play only after acknowledging this token idle.
                        if [ "$token" = "$requested" ] && [ "$state" = idle ] &&
                            [ -n "$filename" ] && [ -n "$digest" ] && [ -z "$extra" ]; then
                            # Latch before spawning so a crash cannot replay this token.
                            rm -f "$progress"
                            report launching
                            clock_id=
                            if [ "${OPERIX_CAMERA_LAB_FRAME_CLOCK:-0}" = 1 ]; then
                                clock_id=$(printf '%s' "$token" | sha256sum | cut -c 1-32)
                            fi
                            VIDEO_PROGRESS_FILE="$progress" VIDEO_PLAY_ONCE=1 VIDEO_FILE="$filename" \
                                OPERIX_LAB_CLOCK_ID="$clock_id" \
                                VIDEO_SHA256="$digest" /bin/sh /lab/publish.sh &
                            child=$!
                        fi
                        ;;
                esac
            fi
        fi
    fi
    if [ -n "$child" ]; then
        if kill -0 "$child" 2>/dev/null; then
            if [ "$state" = playing ] || { [ -r "$progress" ] &&
                awk -F= '$1 == "frame" && $2 > 0 { found = 1; exit } END { exit !found }' "$progress"; }; then
                report playing
            fi
        else
            if wait "$child"; then
                report eof
            else
                report failed
            fi
            child=
        fi
    elif [ -n "$desired" ] && [ "$state" = idle ]; then
        report idle
    fi
    sleep 0.25
done
