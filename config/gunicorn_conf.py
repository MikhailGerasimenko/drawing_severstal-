import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker processes
# Ignore platform WEB_CONCURRENCY (often set from node CPU count).
# Override only via DXF_GUNICORN_WORKERS if you really need more workers + RAM.
workers = int(os.getenv("DXF_GUNICORN_WORKERS", "1"))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
# DXF convert + PNG can exceed the template default 30s
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
keepalive = 2
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "200"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "50"))

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
)

# Process naming
proc_name = "dxf-converter"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None
