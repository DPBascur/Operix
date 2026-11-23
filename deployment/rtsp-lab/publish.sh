#!/bin/sh
set -eu

fail() {
    printf '[%s] %s\n' "$CAMERA_PATH" "$1" >&2
    exit 1
}

case "$VIDEO_FILE" in
    */*|*\\*|.mp4) fail "VIDEO_FILE must be an MP4 basename" ;;
    *.mp4) ;;
    *) fail "VIDEO_FILE must be an MP4 basename" ;;
esac
video="/data/rtsp-lab/$VIDEO_FILE"
[ -f "$video" ] && [ -r "$video" ] && [ ! -L "$video" ] || fail "Cannot read $video"
exec 3< "$video"

case "$VIDEO_SHA256" in
    ""|*[!0-9a-fA-F]*) fail "VIDEO_SHA256 must be a 64-digit hexadecimal digest" ;;
esac
[ "${#VIDEO_SHA256}" -eq 64 ] || fail "VIDEO_SHA256 must be a 64-digit hexadecimal digest"
expected_hash=$(printf '%s' "$VIDEO_SHA256" | tr 'A-F' 'a-f')

for value in "$VIDEO_WIDTH" "$VIDEO_HEIGHT" "$VIDEO_FPS" "$LOOP_GAP_SECONDS"; do
    case "$value" in
        ""|0*|*[!0-9]*) fail "Dimensions, FPS and loop gap must be positive integers" ;;
    esac
done
[ "$VIDEO_WIDTH" -ge 16 ] && [ "$VIDEO_WIDTH" -le 1920 ] &&
    [ "$((VIDEO_WIDTH % 2))" -eq 0 ] || fail "Width must be even and between 16 and 1920"
[ "$VIDEO_HEIGHT" -ge 16 ] && [ "$VIDEO_HEIGHT" -le 1080 ] &&
    [ "$((VIDEO_HEIGHT % 2))" -eq 0 ] || fail "Height must be even and between 16 and 1080"
[ "$VIDEO_FPS" -le 30 ] || fail "FPS must be between 1 and 30"

fit="scale=$VIDEO_WIDTH:$VIDEO_HEIGHT:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1"
canvas="pad=$VIDEO_WIDTH:$VIDEO_HEIGHT:(ow-iw)/2:(oh-ih)/2"

child=
terminate() {
    if [ -n "$child" ]; then
        kill -TERM "$child" 2>/dev/null || true
        wait "$child" || true
    fi
    exit 0
}
trap terminate INT TERM

run_child() {
    "$@" &
    child=$!
    status=0
    wait "$child" || status=$?
    child=
    return "$status"
}

epoch=0
set --
if [ -n "${VIDEO_PROGRESS_FILE:-}" ]; then
    set -- -progress "$VIDEO_PROGRESS_FILE" -stats_period 0.25
fi
while :; do
    checksum=$(sha256sum < /proc/self/fd/3) || fail "Cannot hash $VIDEO_FILE"
    [ "${checksum%% *}" = "$expected_hash" ] || fail "SHA-256 mismatch for $VIDEO_FILE"
    epoch=$((epoch + 1))
    printf '[%s] epoch=%s starting %s\n' "$CAMERA_PATH" "$epoch" "$VIDEO_FILE"
    # One real-time pass to EOF. A fresh RTSP connection starts the next pass.
    status=0
    if run_child ffmpeg "$@" -nostdin -hide_banner -loglevel warning -xerror -abort_on empty_output \
        -re -protocol_whitelist file -f mov -threads 2 -i /proc/self/fd/3 -map 0:v:0 \
        -vf "fps=$VIDEO_FPS,$fit,$canvas" \
        -c:v libx264 -threads 2 -preset veryfast -tune zerolatency \
        -pix_fmt yuv420p -g "$VIDEO_FPS" \
        -f rtsp -rtsp_transport tcp "rtsp://mediamtx:8554/$CAMERA_PATH"; then
        printf '[%s] epoch=%s reached EOF\n' "$CAMERA_PATH" "$epoch"
    else
        status=$?
        printf '[%s] epoch=%s ffmpeg exited with status %s\n' \
            "$CAMERA_PATH" "$epoch" "$status" >&2
    fi
    [ "${VIDEO_PLAY_ONCE:-0}" != 1 ] || exit "$status"
    run_child sleep "$LOOP_GAP_SECONDS"
done
