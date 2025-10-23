#!/bin/bash

# Start Xvfb in the background.
# -nolisten tcp: Safer for containers, prevents network connections to Xvfb.
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp &
XVFB_PID=$! # Store Xvfb's process ID

# Export DISPLAY for all subsequent commands.
export DISPLAY=:99

# --- Robustly wait for Xvfb to be ready ---
# `xdpyinfo` attempts to connect to the X server. We loop until it succeeds.
echo "Waiting for Xvfb to start..."
for i in $(seq 1 10); do
    # Try connecting to the display, redirecting output to /dev/null
    xdpyinfo >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "Xvfb is ready."
        break # Exit loop if successful
    fi
    echo "Attempt $i: Xvfb not ready yet, waiting..."
    sleep 1
done

# Check if xdpyinfo ever succeeded (i.e., Xvfb became ready)
if [ $? -ne 0 ]; then
    echo "Error: Xvfb did not become ready within 10 seconds."
    kill $XVFB_PID # Attempt to clean up Xvfb process
    exit 1 # Exit the script with an error
fi
# --- End Xvfb readiness check ---

# --- Set XDG_RUNTIME_DIR ---
# Choose a suitable ephemeral directory. /tmp is often used in Docker.
# For a root user, /tmp/runtime-root is a common pattern.
# Using UID is more robust, but root (UID 0) is common in Docker.
export XDG_RUNTIME_DIR="/tmp/runtime-${UID:-0}" # Default to 0 if UID is not set
mkdir -p "$XDG_RUNTIME_DIR" # Create the directory if it doesn't exist
chmod 0700 "$XDG_RUNTIME_DIR" # Set secure permissions (read/write/execute only for owner)
echo "XDG_RUNTIME_DIR set to: $XDG_RUNTIME_DIR"
# --- End XDG_RUNTIME_DIR setup ---

# --- Launch test ---
echo "Launching the app to check for startup errors..."
# We expect timeout to kill the app, which is a success (exit code 124).
# Any other exit code means the app crashed or exited prematurely.
timeout 5s dbus-launch --exit-with-session soundconverter
LAUNCH_STATUS=$?

if [ $LAUNCH_STATUS -eq 124 ]; then
    echo "App launch test successful (killed by timeout as expected)."
else
    echo "Error: App launch test failed with exit code $LAUNCH_STATUS."
    # Clean up Xvfb and exit with the failure code.
    kill $XVFB_PID
    exit $LAUNCH_STATUS
fi

# --- End of launch test ---
# Start a D-Bus session for GTK applications and run pytest within it.
# `dbus-launch --exit-with-session`: Ensures a D-Bus session is started,
# and it automatically exits when the wrapped command finishes.
echo "Starting tests within a D-Bus session..."
dbus-launch --exit-with-session python3 /app/tests/test.py /app/builddir
errors=$?

# Ensure Xvfb process is killed after tests, even if dbus-launch didn't clean it up for some reason.
# `wait` prevents the script from exiting immediately, giving Xvfb a chance to respond to the kill.
kill $XVFB_PID
wait $XVFB_PID 2>/dev/null # Suppress "No such process" if already exited

exit $errors
