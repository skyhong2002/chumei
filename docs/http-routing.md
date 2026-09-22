# Production HTTP routing

`deploy/chumei.caddy` is the complete `chumei.observe.tw` vhost. It serves the
atomic publisher's `published/current` release and preserves the MCP, LINE,
Web Push, auth/account, submissions, contributions, public profile and custom
feed reverse proxies. Other hostnames and global Caddy options stay in the
host's existing Caddyfile.

Unknown pages and event URLs return HTTP **404**, with `site/404.html`, a search
form and links home. Missing assets, data and feed files return a plain-text
404, including when the client sends `Accept: text/html`. Existing directory
indexes keep canonical slash redirects; generated merged-event redirect HTML
continues to work. Backend responses remain the responsibility of each proxy
service. The 404 HTML and response header both request `noindex`.

## Activation

1. Publish a validated release using `scripts/publish_site.py` (see
   [atomic publication](atomic-publication.md)). Verify that
   `published/current/404.html` exists **before** switching the server root.
2. Back up the active Caddyfile, then replace **only** its
   `chumei.observe.tw { ... }` block with `deploy/chumei.caddy`. Do not replace
   the full multi-host Caddyfile or alter its global settings.
3. Run `/usr/local/sbin/caddy validate --config /path/to/active/Caddyfile
   --adapter caddyfile`, then reload that same config using the existing Caddy
   service. Validation must pass before reload.
4. Check `/`, `/events/`, a known `/event/<id>/`, `/auth/me`, and a custom feed;
   verify a random `/event/missing-<timestamp>/` returns 404 with recovery links
   and `/assets/missing-<timestamp>.js` returns 404 with `text/plain`.

For rollback, restore the backed-up vhost and reload the validated config.
The previous published release remains available through the publisher's
rollback mechanism. No application service port needs changing.

## Regression check

```sh
python3 -m unittest discover -s tests -p test_caddy_routes.py -v
/usr/local/sbin/caddy validate --config deploy/chumei.caddy --adapter caddyfile
```

The integration test launches a temporary Caddy on loopback port 18991 and a
mock backend on 18992, with the admin API disabled and isolated Caddy storage.
It checks real response statuses, content types, search/home recovery,
canonical directory redirects, a merged-event redirect page and all current
proxy routes. It never reloads or contacts the production Caddy admin API.
Install Caddy in environments running this optional integration test; otherwise
unittest explicitly reports it as skipped.

Caddy's [error handler documentation](https://caddyserver.com/docs/caddyfile/directives/handle_errors)
confirms that `file_server` preserves the error HTTP status inside
`handle_errors`. There is intentionally no homepage fallback in the static
handler.
