# Enzo Peres Afonso 2025
import cv2
import pyaudio
import threading
import queue
import time
import numpy as np
from flask import Flask, Response, render_template_string
import socket
import sys
import signal
from typing import Optional, Iterator, Tuple

# --- Configuration ---
# Audio Settings
CHUNK: int = 1024 * 2          # Audio chunk size
FORMAT = pyaudio.paInt16    # Audio format (16-bit Signed Integer)
CHANNELS: int = 1                # Number of audio channels (1 for Mono)
RATE: int = 48000                # ** IMPORTANT: Sample rate (samples per second). Check your microphone's supported rates!
                                 # Common rates: 48000, 44100, 32000, 16000, 8000. See README.
AUDIO_DEVICE_INDEX: Optional[int] = None   # Set manually if auto-detection fails (see script output)

# Video Settings
VIDEO_DEVICE_INDEX: int = 0      # Camera index (usually 0 for default USB camera)
FRAME_WIDTH: int = 640           # Desired video width
FRAME_HEIGHT: int = 480          # Desired video height
FRAME_RATE: int = 24             # Desired video frame rate (camera might adjust)

# Streaming Settings
JPEG_QUALITY: int = 75           # JPEG quality for video frames (0-100)

# --- End Configuration ---

# Queues to hold captured data (with limited size)
audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=10)
video_queue: queue.Queue[bytes] = queue.Queue(maxsize=2)

# Flag to signal threads to stop
stop_event = threading.Event()

# Global PyAudio instance
p: Optional[pyaudio.PyAudio] = None

# --- Audio Capture Thread ---
def find_audio_device_index(p_instance: pyaudio.PyAudio, target_name_part: str ="USB") -> Optional[int]:
    """Helper to find the index of an audio input device."""
    print("\n--- Searching for Audio Input Devices ---")
    target_index: Optional[int] = None
    default_device_index: Optional[int] = None

    try:
        default_info = p_instance.get_default_input_device_info()
        default_device_index = default_info['index']
        print(f"Default Input Device: Index {default_info['index']} - {default_info['name']}")
    except IOError:
        print("Warning: No default input device found.")

    print("Available Audio Input Devices:")
    for i in range(p_instance.get_device_count()):
        info = p_instance.get_device_info_by_index(i)
        is_input = info.get('maxInputChannels', 0) > 0
        if is_input:
            print(f"  Index {i}: {info.get('name')} (Input Channels: {info.get('maxInputChannels')})")
            # Prioritize devices matching the target name
            if target_name_part.lower() in info.get('name', '').lower():
                if target_index is None: # Found the first match
                    target_index = i
                    print(f"    -> Found potential match: '{info.get('name')}'")
                else:
                    print(f"    -> Found another potential match: '{info.get('name')}' (using first found: Index {target_index})")

    if target_index is not None:
        print(f"--- Automatically selected Index {target_index} based on name '{target_name_part}' ---")
        return target_index
    elif default_device_index is not None:
        print(f"--- Could not find device with '{target_name_part}', using default input Index {default_device_index} ---")
        return default_device_index
    else:
        print(f"\n--- ERROR: Could not automatically find an audio device containing '{target_name_part}' and no default input device available.")
        print("--- Please check your microphone connection and ALSA configuration. ---")
        print("--- You may need to manually set AUDIO_DEVICE_INDEX in the script. ---")
        print("--- Run 'arecord -l' in the terminal to list capture devices. ---")
        return None

def get_alsa_device_name(p_instance: pyaudio.PyAudio, index: int) -> Optional[str]:
    """Try to get the ALSA device name (e.g., hw:1,0) for better error messages."""
    try:
        info = p_instance.get_device_info_by_index(index)
        name = info.get('name')
        # Extract hw:X,Y from names like "webcam: USB Audio (hw:1,0)"
        if name and '(hw:' in name:
            start = name.find('(hw:') + 1
            end = name.find(')', start)
            if start != 0 and end != -1:
                return name[start:end]
    except Exception:
        pass # Ignore errors just trying to get the name
    return None


def capture_audio(p_instance: pyaudio.PyAudio, audio_idx: int) -> None:
    """Captures audio chunks and puts them into the audio_queue."""
    stream = None
    try:
        print(f"Attempting to open audio stream on device index {audio_idx}...")
        stream = p_instance.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 frames_per_buffer=CHUNK,
                                 input_device_index=audio_idx)
        print("Audio stream opened successfully.")

        while not stop_event.is_set():
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                # Non-blocking put with overwrite of oldest if full
                if audio_queue.full():
                    try:
                        audio_queue.get_nowait()
                        # print("Audio queue full, discarding oldest chunk.") # Can be noisy
                    except queue.Empty:
                        pass
                audio_queue.put_nowait(data)
            except IOError as e:
                # Handle input overflow gracefully if possible
                if e.errno == pyaudio.paInputOverflowed:
                     print("Warning: Audio input overflowed.", file=sys.stderr)
                     continue # Try to continue reading
                else:
                    print(f"Audio read error: {e}", file=sys.stderr)
                    stop_event.set() # Signal other threads to stop on critical error
                    break
            except queue.Full:
                 # Should be rare with the check above, but handle anyway
                 pass

    except OSError as e:
        # This specifically catches errors like invalid sample rate during stream opening
        print(f"\n--- FATAL ERROR initializing audio stream ---", file=sys.stderr)
        print(f"Error details: {e}", file=sys.stderr)
        if e.errno == pyaudio.paInvalidSampleRate: # Check if it's the invalid sample rate error
            print(f"*** The configured sample rate ({RATE} Hz) is likely NOT SUPPORTED by device index {audio_idx}.", file=sys.stderr)
            alsa_name = get_alsa_device_name(p_instance, audio_idx)
            print("*** Please check your hardware's capabilities.", file=sys.stderr)
            if alsa_name:
                 print(f"*** Try running this command in the terminal to see supported rates for '{alsa_name}':", file=sys.stderr)
                 print(f"    arecord --dump-hw-params -D {alsa_name}", file=sys.stderr)
            else:
                 print(f"*** Try running 'arecord -l' to find your device's card/device number (e.g., card 1, device 0 -> hw:1,0)", file=sys.stderr)
                 print(f"*** Then run 'arecord --dump-hw-params -D hw:X,Y' (replace X,Y).", file=sys.stderr)
            print(f"*** Then, edit the 'RATE' variable in this script and restart.", file=sys.stderr)
        elif e.errno == pyaudio.paInvalidDevice:
             print(f"*** Invalid audio device index ({audio_idx}). Check connection and 'arecord -l'.", file=sys.stderr)
        stop_event.set()
    except Exception as e:
        print(f"FATAL ERROR in audio capture thread: {e}", file=sys.stderr)
        stop_event.set()
    finally:
        print("Stopping audio capture...")
        if stream is not None:
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
            except Exception as e:
                print(f"Error closing audio stream: {e}", file=sys.stderr)


# --- Video Capture Thread ---
def capture_video() -> None:
    """Captures video frames using OpenCV and puts them into the video_queue."""
    cap = None
    try:
        print(f"Attempting to open video stream on device index {VIDEO_DEVICE_INDEX}...")
        cap = cv2.VideoCapture(VIDEO_DEVICE_INDEX)
        if not cap.isOpened():
            print(f"--- ERROR: Could not open video device {VIDEO_DEVICE_INDEX}. ---", file=sys.stderr)
            print("--- Please ensure the webcam is connected and detected (run 'v4l2-ctl --list-devices'). ---", file=sys.stderr)
            stop_event.set()
            return

        print("Video device opened successfully.")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FRAME_RATE)

        actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"Video capture started: {int(actual_width)}x{int(actual_height)} @ {actual_fps:.2f} FPS (requested {FRAME_WIDTH}x{FRAME_HEIGHT} @ {FRAME_RATE} FPS)")

        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                print("Warning: Failed to grab frame from camera. Retrying...", file=sys.stderr)
                time.sleep(0.1) # Wait briefly before retrying
                continue

            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if not ret:
                print("Warning: Failed to encode frame to JPEG.", file=sys.stderr)
                continue

            frame_bytes = buffer.tobytes()

            # Non-blocking put with overwrite of oldest if full
            if video_queue.full():
                try:
                    video_queue.get_nowait()
                except queue.Empty:
                    pass
            video_queue.put_nowait(frame_bytes)

            # Small sleep to prevent high CPU usage if capture is very fast
            # time.sleep(0.01) # Optional: Adjust if needed

    except Exception as e:
        print(f"FATAL ERROR in video capture thread: {e}", file=sys.stderr)
        stop_event.set()
    finally:
        print("Stopping video capture...")
        if cap is not None:
            cap.release()


# --- Flask Web Server ---
app = Flask(__name__)

# -- Audio Streaming ---
def generate_audio() -> Iterator[bytes]:
    """Generator function to stream audio chunks."""
    print("Audio client connected.")
    while not stop_event.is_set():
        try:
            chunk = audio_queue.get(timeout=1.0) # Wait up to 1s for audio data
            yield chunk
        except queue.Empty:
            # If the queue is empty for a second, maybe the capture thread stopped
            if stop_event.is_set():
                print("Audio capture stopped, closing stream for client.")
                break
            else:
                continue # Keep waiting if capture thread is still running
        except Exception as e:
            print(f"Error yielding audio chunk: {e}", file=sys.stderr)
            break
    print("Audio client disconnected.")

@app.route('/audio.raw')
def audio_feed():
    """Route to stream raw audio."""
    # Check if audio thread failed to start
    if audio_thread is None or not audio_thread.is_alive() and not audio_queue.qsize() > 0 :
         return "Audio capture failed to start or has stopped. Check server console.", 503 # Service Unavailable
    return Response(generate_audio(),
                    mimetype='application/octet-stream',
                    headers={'Content-Disposition': 'attachment; filename=audio.raw'})

# -- Video Streaming ---
def generate_video() -> Iterator[bytes]:
    """Generator function to stream MJPEG video."""
    print("Video client connected.")
    while not stop_event.is_set():
        try:
            frame_bytes = video_queue.get(timeout=1.0) # Wait up to 1s for a frame
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except queue.Empty:
             if stop_event.is_set():
                 print("Video capture stopped, closing stream for client.")
                 break
             else:
                 # Could send a placeholder image here if desired
                 continue # Keep waiting
        except Exception as e:
            print(f"Error yielding video frame: {e}", file=sys.stderr)
            break
    print("Video client disconnected.")

@app.route('/video.mjpeg')
def video_feed():
    """Route to stream MJPEG video."""
    if not video_thread.is_alive() and not video_queue.qsize() > 0 :
         return "Video capture failed to start or has stopped. Check server console.", 503
    return Response(generate_video(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# -- Simple HTML Page ---
@app.route('/')
def index():
    """Serves a simple HTML page with controls and stream info."""
    host_ip = 'YOUR_PI_IP' # Default placeholder
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)) # Connect to external server to find local IP
        host_ip = s.getsockname()[0]
        s.close()
    except Exception:
        print("Warning: Could not automatically determine host IP address.")

    # Use the actual audio index chosen by the script
    display_audio_index = final_audio_index if final_audio_index is not None else 'Not Found/Set'

    # Simple HTML with placeholders filled by Flask
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Raspberry Pi Live Stream</title>
        <style> body { font-family: sans-serif; } code { background-color: #f0f0f0; padding: 2px 5px; border-radius: 3px; } </style>
    </head>
    <body>
        <h1>SAAO IO piStream Status</h1>

        <h2>Video Feed (MJPEG)</h2>
        <img src="{{ url_for('video_feed') }}" width="{{ width }}" height="{{ height }}" alt="Live video stream">
        <p>Video Device Index: <code>{{ video_idx }}</code> | Resolution: <code>{{ width }}x{{ height }}</code> | Target FPS: <code>{{ fps }}</code></p>

        <h2>Audio Feed (Raw PCM)</h2>
        <p>
            Raw audio stream URL:
            <a href="{{ url_for('audio_feed') }}" target="_blank"><code>{{ url_for('audio_feed') }}</code></a>
        </p>
        <p>
            Audio Device Index: <code>{{ audio_idx }}</code> | Format: <code>{{ channels }} channel(s), {{ rate }} Hz, 16-bit Signed Int (pcm_s16le)</code>
        </p>
        <p>
            <b>Listen using <code>aplay</code> (requires <code>alsa-utils</code> on client):</b><br>
            <code>curl -N http://{{ host }}:{{ port }}{{ url_for('audio_feed') }} | aplay -r {{ rate }} -f S16_LE -c {{ channels }} -</code>
            <br><small>(Ensure <code>-r</code>, <code>-f</code>, <code>-c</code> match the parameters above)</small>
        </p>

        <hr>
        <h3>Troubleshooting Tips:</h3>
        <ul>
            <li><b>Check Console Output:</b> Look for error messages in the terminal where you ran the script on the Raspberry Pi.</li>
            <li><b>No Video / Frozen:</b> Verify <code>VIDEO_DEVICE_INDEX</code> ({{ video_idx }}) in the script. Run <code>v4l2-ctl --list-devices</code> on the Pi. Ensure camera isn't used elsewhere.</li>
            <li><b>No Audio / Error Message:</b>
                <ul>
                <li>Verify <code>AUDIO_DEVICE_INDEX</code> ({{ audio_idx }}) in the script matches your mic (check script startup logs & <code>arecord -l</code>).</li>
                <li>Verify <code>RATE</code> ({{ rate }}) is supported by your mic. Check console for 'Invalid sample rate' errors. Use <code>arecord --dump-hw-params -D hw:X,Y</code> (find X,Y from <code>arecord -l</code>) to see supported rates.</li>
                <li>Ensure client <code>aplay</code> command parameters match the stream format exactly.</li>
                </ul>
            </li>
             <li><b>Permission Denied:</b> Ensure the user running the script has access to audio/video devices (usually okay by default on Pi OS, but check group memberships: <code>groups $USER</code> should ideally include <code>audio</code> and <code>video</code>).</li>
        </ul>
    </body>
    </html>
    """
    return render_template_string(html_content,
                                  width=FRAME_WIDTH, height=FRAME_HEIGHT, fps=FRAME_RATE, video_idx=VIDEO_DEVICE_INDEX,
                                  channels=CHANNELS, rate=RATE, audio_idx=display_audio_index,
                                  host=host_ip, port=5000) # Assuming default port 5000


# --- Signal Handling and Main Execution ---
audio_thread: Optional[threading.Thread] = None
video_thread: Optional[threading.Thread] = None
final_audio_index: Optional[int] = None # Keep track of the used audio index globally for the index page

def signal_handler(sig, frame):
    """Handle termination signals (like Ctrl+C) gracefully."""
    print("\nSignal received, shutting down...")
    stop_event.set()
    # Allow threads a moment to finish
    time.sleep(0.5)
    # No need to explicitly join daemon threads if we're exiting
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Handle termination signals

    try:
        p = pyaudio.PyAudio()

        # --- Find and Set Audio Device ---
        auto_audio_index = find_audio_device_index(p)
        final_audio_index = AUDIO_DEVICE_INDEX if AUDIO_DEVICE_INDEX is not None else auto_audio_index

        print("-" * 30)
        if final_audio_index is not None:
             print(f"Selected Audio Device Index: {final_audio_index}")
             print(f"Using Audio Settings: {CHANNELS}ch, {RATE}Hz, 16-bit PCM")
        else:
             print("WARNING: No suitable audio device index found or set. Audio streaming will be disabled.")
        print("-" * 30)

        # --- Start Capture Threads ---
        if final_audio_index is not None:
            audio_thread = threading.Thread(target=capture_audio, args=(p, final_audio_index), daemon=True)
            audio_thread.start()
        else:
            audio_thread = None # Explicitly mark as not started

        video_thread = threading.Thread(target=capture_video, daemon=True)
        video_thread.start()

        # Give threads a moment to initialize and potentially fail early
        time.sleep(1.0)
        if stop_event.is_set(): # Check if any thread failed during init
             print("\n--- A capture thread failed to initialize. Exiting. Check errors above. ---", file=sys.stderr)
             raise SystemExit # Or sys.exit(1)

        # --- Start Flask Server ---
        print("\nStarting Flask development server...")
        print(f"Access the web interface at: http://<YOUR_PI_IP>:5000/")
        # Note: Use a production WSGI server (like Gunicorn or Waitress) for deployment
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False, use_reloader=False)

    except Exception as e:
         print(f"An unexpected error occurred in the main execution: {e}", file=sys.stderr)
    finally:
        # --- Cleanup ---
        print("\nShutting down...")
        stop_event.set() # Signal threads one last time

        # Wait briefly for threads to potentially clean up (daemons might exit abruptly)
        # If cleaner shutdown needed, remove daemon=True and explicitly join() threads
        time.sleep(0.5)

        if p is not None:
            p.terminate()
            print("PyAudio terminated.")

        print("Server stopped.")