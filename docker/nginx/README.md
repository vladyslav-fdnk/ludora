# docker/nginx

Reverse proxy configuration used by `docker-compose.prod.yml`.

`nginx.conf`:

- serves collected static files from `/srv/static/` and uploaded media from
  `/srv/media/` (shared Docker volumes);
- proxies all other requests to gunicorn at `backend:8000`, resolving the
  backend through Docker's DNS so a recreated backend container is picked up
  without restarting nginx;
- forwards `X-Forwarded-Proto`, keeping the original scheme when TLS is
  terminated in front of nginx.

nginx listens on plain HTTP. Terminate TLS in front of it (a cloud load
balancer, Caddy, or certbot on the host) and set
`DJANGO_BEHIND_HTTPS_PROXY=True`.

The development `docker-compose.yml` does not use nginx; it exposes Django's
development server directly.

---

_README written with the assistance of Claude (Anthropic)._
