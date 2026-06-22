bind = "0.0.0.0:5000"
workers = 2
worker_class = "sync"
timeout = 120
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"
