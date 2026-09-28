# heatzyd

heatzyd is a self-hosted web app as an alternative to the official [Heatzy](https://www.heatzy.com/) application, to manage your heating devices.

## Tech stack

 - Architecture: hypermedia-driven (HTMX + Jinja2),
 - Backend: FastAPI,
 - Templates: Jinja2,
 - Frontend: [htmx 4](https://four.htmx.org/) with [hx-sse](https://four.htmx.org/extensions/hx-sse), Bootstrap 5,
 - Storage: SQLModel + SQLite,
 - Runtime: Python 3.14, uv.

## Features

 - List your devices,
 - Send an order: Comfort, Comfort -1, Comfort -2, Eco, Frost-free, Off,
 - Toggle the lock switch,
 - Realtime refresh,
 - Login / logout with your Heatzy account.

## Supported devices

Only the **Pilote 3** (2022) is tested and supported for now. The other Heatzy models are planned.

## Roadmap

 - [x] Sending order to device,
 - [x] Realtime refresh,
 - [x] Device lock control,
 - [ ] Device detail page,
 - [ ] Boost (native derogation),
 - [ ] Holidays mode, per device and multi-device at once,
 - [ ] New scheduler,
 - [ ] Rename a device,
 - [ ] Support for the other Heatzy models (1st gen pilot, etc.).

## Installation

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run fastapi dev
```

Then open http://127.0.0.1:8000, and log in with your Heatzy credentials.

## Notes

heatzyd is single-user and should stay on a private network (VPN).
The "login"is the Heatzy credential input, not an application account. Credentials are stored in clear text in the database for now.

## Use of AI

AI is used for code review and documentation generation. The `scripts` directory contains generated code.
