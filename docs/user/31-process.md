---
section: Using Harness Maxxing
---
# Process

**Process** (sidebar, shortcut `g` then `p`) lists the commands you run in your repositories: a dev server, a build,
a long task. They run on the server, so they keep going when you close the page, and you can follow them from
anywhere.

## Start one

**New process**: a name, the repository folder (absolute path on the server, or relative to the workspace) and the
command, for example `npm run dev -- --port $PORT`. The variable `PORT` holds a free local port (20000-29999);
`HOST` is `127.0.0.1`. Each process is its own system unit: it is not tied to a session, and a crash of one never
touches the others or Harness.

Each card shows the state, the uptime, the CPU and memory, and **Start / Stop / Restart**, the **Logs** (the last 300
lines, live) and **Remove** (stops it, removes its URL and logs; the repository is untouched).

## A URL, behind a password

**Get a URL** publishes the process through Caddy over HTTPS with a generated password (HTTP basic authentication,
user `maxxing`). Nobody opens it without the password; it is shown in **Password**, and stored hashed in Caddy.
**Remove URL** closes it at once.

- Default: `https://<your Harness address>/p-<name>/`. No DNS to set. The page runs in a sandbox (the same one as
  `maxxing infra site add`): it cannot reach Harness, but it has no cookies or local storage of its own, and it
  must work under a sub-path. Fine for a static site or a simple app.
- With a **host name** (`app.example.com`, its DNS record pointing to this server): the app has its own address,
  without those limits. Use this for a real app with a login.

The process must listen on `127.0.0.1:$PORT`.

## Good to know

- Commands run as the server's user (root by default), like a session: only start what you trust.
- A process that exits shows as **Stopped**; its last output stays in the logs.
- Processes keep running through a Harness update, and are not restarted by a server reboot: start them again.
