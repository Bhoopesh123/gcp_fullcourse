#!/bin/bash
set -e

# Update & install prerequisites
apt-get update -y
apt-get install -y python3-pip python3-venv

# Create an app user if not present
id -u appuser &>/dev/null || useradd -m -s /bin/bash appuser

# Switch to appuser and set up a virtual environment
sudo -u appuser bash <<'EOF'
cd ~
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask gunicorn

# Create Flask app
cat > app.py <<PY
from flask import Flask
app = Flask(__name__)

@app.route("/")
def index():
    return "Hello from Flask on GCP (private subnet)!"

@app.route("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
PY
EOF

# Create systemd service using venv's Gunicorn
cat >/etc/systemd/system/flask.service <<'UNIT'
[Unit]
Description=Flask via Gunicorn in venv
After=network.target

[Service]
User=appuser
WorkingDirectory=/home/appuser
ExecStart=/home/appuser/venv/bin/gunicorn -w 2 -b 0.0.0.0:8080 app:app
Restart=always

[Install]
WantedBy=multi-user.target
UNIT

# Enable and start service
systemctl daemon-reload
systemctl enable --now flask.service