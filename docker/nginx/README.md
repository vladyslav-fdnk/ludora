# docker/nginx

Reserved for a future reverse proxy in front of the Django backend, for
example an `nginx.conf`, TLS termination, and static/media file serving.

It is not used by `docker-compose.yml`. The current Compose file is a local
development topology and exposes Django's development server directly.
