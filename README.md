# Raspberry Pi USB Webcam Audio/Video Streamer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Streams video (MJPEG) and audio (Raw PCM) from a USB webcam connected to a Raspberry Pi over the network via a simple web interface. Includes auto-detection for USB audio devices and clear troubleshooting guidance.

**Author:** Enzo Peres Afonso (2025)

## Features

*   Streams video via MJPEG, viewable directly in most web browsers.
*   Streams raw audio (PCM s16le), playable using tools like `aplay`.
*   Simple web interface showing video feed and instructions.
*   Automatic detection of USB audio input devices (can be overridden manually).
*   Configurable video resolution, frame rate, and audio settings.
*   Uses threading for concurrent audio/video capture and streaming.
*   Includes basic troubleshooting tips in the web UI and console output.
*   Graceful shutdown on Ctrl+C.

## Hardware Requirements

*   Raspberry Pi (tested on Pi 3B+, Pi 4, should work on others)
*   USB Webcam with built-in microphone (or a separate USB microphone)
*   Power Supply for Raspberry Pi
*   SD Card with Raspberry Pi OS (or similar Linux distribution)
*   Network connection (Ethernet or WiFi)

## Software Prerequisites

1.  **Operating System:** Raspberry Pi OS (Legacy/Bullseye/Bookworm) recommended.
2.  **Python:** Python 3.7+
3.  **pip:** Python package installer.
4.  **System Libraries:**
    *   `portaudio19-dev`: Required by PyAudio for audio I/O.
    *   `libatlas-base-dev`: Often needed for NumPy optimizations.
    *   `libopenjp2-7`: Dependency for OpenCV image formats.
    *   `libavcodec-dev`, `libavformat-dev`, `libswscale-dev`: FFmpeg libraries used by OpenCV.
    *   `v4l-utils`: Useful for listing and testing video devices (`v4l2-ctl --list-devices`).
    *   `alsa-utils`: Useful for listing and testing audio devices (`arecord -l`, `aplay`).

## Installation

1.  **Update System & Install Prerequisites:**
    Open a terminal on your Raspberry Pi and run:
    ```bash
    sudo apt update
    sudo apt upgrade -y
    sudo apt install -y python3-pip python3-venv portaudio19-dev libatlas-base-dev libopenjp2-7 libavcodec-dev libavformat-dev libswscale-dev v4l-utils alsa-utils git
    ```
    *(Note: Some dependencies might already be installed)*

2.  **Clone the Repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/pi-webcam-stream.git # Replace YOUR_USERNAME!
    cd pi-webcam-stream
    ```

3.  **Set up Python Virtual Environment (Recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    # To deactivate later, just type 'deactivate'
    ```

4.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Most configuration options are at the top of the `stream_server.py` script. Edit this file before running if needed:

*   **`AUDIO_DEVICE_INDEX`**: Leave as `None` to attempt auto-detection (searches for "USB" in the device name). If auto-detection fails or selects the wrong device, set this manually to the correct index number. Run the script once to see the list of detected devices and their indices, or use `arecord -l` in the terminal.
*   **`VIDEO_DEVICE_INDEX`**: Usually `0` for the default USB webcam. Change if you have multiple cameras. Use `v4l2-ctl --list-devices` to check.
*   **`RATE`**: **Crucial!** Audio sample rate. `48000` or `44100` are common, but **must** match what your microphone supports. If you get "Invalid sample rate" errors, check the script's console output for instructions on using `arecord --dump-hw-params` to find supported rates.
*   **`CHANNELS`**: Typically `1` for mono microphones.
*   **`FRAME_WIDTH`, `FRAME_HEIGHT`, `FRAME_RATE`**: Desired video resolution and FPS. The camera may not support all combinations; the script will report the actual settings used. Lower values reduce CPU load and network bandwidth.
*   **`JPEG_QUALITY`**: Video compression quality (0-100). Lower values reduce bandwidth but decrease quality. `75` is a reasonable default.

## Running the Stream

1.  **Ensure Virtual Environment is Active (if used):**
    ```bash
    source venv/bin/activate
    ```

2.  **Run the Server:**
    ```bash
    python stream_server.py
    ```

3.  **Access the Stream:**
    *   The script will print messages indicating which audio/video devices are being used and if the server started successfully.
    *   Find your Raspberry Pi's IP address (e.g., run `hostname -I` in another terminal).
    *   Open a web browser on another computer on the same network and go to: `http://<YOUR_PI_IP>:5000` (replace `<YOUR_PI_IP>`).
    *   You should see the video stream and instructions for accessing the audio stream.

4.  **Listening to Audio:**
    The web page provides an example command using `aplay` (part of `alsa-utils`). You'll need `alsa-utils` and `curl` installed on the *client* machine listening to the audio:
    ```bash
    # On the client machine (e.g., your laptop):
    # Make sure rate (-r), format (-f), channels (-c) match the server config!
    curl -N http://<YOUR_PI_IP>:5000/audio.raw | aplay -r 48000 -f S16_LE -c 1 -
    ```

## Stopping the Server

Press `Ctrl+C` in the terminal where the script is running.

## Troubleshooting

*   **Check Console Output:** The script prints detailed information about device detection, errors, and chosen settings when it starts. Look here first!
*   **No Video / "Could not open video device"**:
    *   Verify the camera is securely connected.
    *   Check `VIDEO_DEVICE_INDEX` in `stream_server.py`.
    *   Run `v4l2-ctl --list-devices` on the Pi to see detected video devices and their paths (e.g., `/dev/video0`).
    *   Ensure the camera isn't being used by another application.
    *   Try a lower resolution/framerate.
*   **No Audio / "Error initializing audio stream" / "Invalid sample rate"**:
    *   Verify the microphone is connected.
    *   Check `AUDIO_DEVICE_INDEX` in `stream_server.py`. Let the script run once to see the detected devices and indices, or use `arecord -l`.
    *   **Verify the `RATE` setting.** This is the most common audio issue. Use the `arecord --dump-hw-params -D hw:X,Y` command (find `X,Y` from `arecord -l`) as suggested in the script's error output to find the rates your hardware *actually* supports. Edit `stream_server.py` and restart.
    *   Ensure the user running the script has permissions for audio devices (usually ok if in the `audio` group - check with `groups $USER`).
*   **Audio Sounds Bad / Glitchy:**
    *   Could be network congestion or high CPU load on the Pi. Try lowering video resolution/framerate/quality.
    *   Ensure the `aplay` parameters on the client exactly match the server's `RATE`, `FORMAT` (S16_LE = 16-bit signed little-endian), and `CHANNELS`.
*   **Permission Denied Errors:** Add the current user to the `video` and `audio` groups: `sudo usermod -aG video $USER` and `sudo usermod -aG audio $USER`. You may need to log out and log back in for changes to take effect.
*   **High CPU Usage:** Streaming video, especially encoding, can be demanding. Lowering `FRAME_WIDTH`, `FRAME_HEIGHT`, `FRAME_RATE`, or `JPEG_QUALITY` can help significantly.
