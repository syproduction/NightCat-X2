import subprocess
import threading
import http.server
import socketserver

PORT = 8081

class MJPEGHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header('Age', '0')
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.end_headers()

        # Start v4l2-ctl process
        v4l2_proc = subprocess.Popen([
            "v4l2-ctl", "--device=/dev/video0",
            "--set-fmt-video=width=256,height=392,pixelformat=YUYV",
            "--stream-mmap", "--stream-to=-", "--stream-count=0"
        ], stdout=subprocess.PIPE)

        # Start ffmpeg process
        ffmpeg_proc = subprocess.Popen([
            "ffmpeg",
            "-f", "rawvideo",
            "-pixel_format", "yuyv422",
            "-video_size", "256x392",
            "-framerate", "25",
            "-i", "-",
            "-f", "image2pipe",
            "-vf", "crop=256:196:0:196,format=yuv420p",
            "-qscale:v", "5",
            "-vcodec", "mjpeg",
            "-"
        ], stdin=v4l2_proc.stdout, stdout=subprocess.PIPE)

        buffer = b""
        try:
            while True:
                chunk = ffmpeg_proc.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk

                # Search for JPEG frame markers
                while True:
                    start = buffer.find(b'\xff\xd8')  # Start of JPEG
                    end = buffer.find(b'\xff\xd9')    # End of JPEG
                    if start != -1 and end != -1 and end > start:
                        frame = buffer[start:end+2]
                        buffer = buffer[end+2:]

                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                    else:
                        break
        except BrokenPipeError:
            print("Client disconnected.")
        finally:
            v4l2_proc.terminate()
            ffmpeg_proc.terminate()

def run_server():
    with socketserver.TCPServer(("", PORT), MJPEGHandler) as httpd:
        print(f"Serving MJPEG on http://0.0.0.0:{PORT}")
        httpd.serve_forever()

if __name__ == '__main__':
    run_server()
