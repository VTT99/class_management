# Self-hosting on a Raspberry Pi at home

End state: the app runs on your Pi at home, reachable from any browser
on the internet as `http://<your-public-ip>:8000/class_management/`
(optionally upgraded to `https://yourname.duckdns.org/class_management/`
once DDNS is in place).

The Pi software setup is almost identical to the VPS walkthrough in
[`DEPLOY.md`](DEPLOY.md). This doc adds the **Pi-specific prep**
(64-bit OS flash, SSH-in) and the **home-network plumbing** (static LAN
IP on the Pi, port forwarding on the router, optional dynamic DNS).

## Hardware

Any Pi 3, Pi 4, Pi 5, or Pi Zero 2 W will work. The Pi 3 you already
have is enough for this app — peak RAM is ~200 MB. Pi Zero 2 W with 512
MB is tight but works. Avoid the original Pi Zero or any older Pi 1/2.

Also need:

- An SD card ≥ 8 GB (16 GB more comfortable). Class 10 / A1+.
- An Ethernet cable if possible (much more reliable than Wi-Fi for a
  24/7 server). Most home routers have spare LAN ports.
- A 5 V / 3 A power supply (the official one — cheap chargers cause
  silent under-voltage that corrupts the SD card).

## 1. Flash 64-bit Raspberry Pi OS

Download **Raspberry Pi Imager** on your laptop:
<https://www.raspberrypi.com/software/>.

In Imager:

- **Device** → your Pi model.
- **Operating System** → **Raspberry Pi OS (other)** → **Raspberry Pi
  OS Lite (64-bit)**. *Lite* means no desktop — fine for a server, much
  faster to boot, no wasted RAM.
- **Storage** → your SD card.
- **Settings** (gear icon):
  - Hostname: `tutorial-pi` (or whatever)
  - Enable SSH with password auth (or key auth if you have a key)
  - Set username + password (write them down)
  - Configure Wi-Fi (skip if using Ethernet — *recommended*)
  - Locale: your timezone

Flash, then put the SD card in the Pi, plug Ethernet, power it up.

## 2. SSH into the Pi

From your laptop:

```bash
ssh you@tutorial-pi.local
```

(or by IP, see step 3). If that hangs, find the Pi's IP via your
router's admin page (usually `http://192.168.1.1` or similar — look for
the DHCP / connected-devices list).

## 3. Give the Pi a static LAN IP

You want the Pi's LAN IP to never change so port-forwarding rules stay
valid. Two ways:

**Option A (preferred): DHCP reservation in your router.** Log into
the router, find the section called "DHCP Reservation" / "Address
Reservation" / "Static Leases". Bind the Pi's MAC address to a fixed
IP, e.g. `192.168.1.50`.

**Option B: configure the Pi directly.** Edit `/etc/dhcpcd.conf`:

```bash
sudo nano /etc/dhcpcd.conf
```

Append (using your router's actual IP for `routers` and the IP you
want for the Pi):

```
interface eth0
static ip_address=192.168.1.50/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 1.1.1.1
```

Save, then `sudo reboot`.

## 4. Install the app

Now follow the same flow as [`DEPLOY.md`](DEPLOY.md), but with these Pi
adjustments (run on the Pi, after SSH-ing in):

```bash
# Tools the Pi might not have:
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# Dedicated system user:
sudo adduser --system --group --home /opt/class_management --shell /usr/sbin/nologin class-management

# Clone the repo:
sudo -u class-management git clone https://github.com/VTT99/class_management.git /opt/class_management
cd /opt/class_management

# Create venv. The --prefer-binary flag saves you from a 30-min
# C++ compile of duckdb if a wheel isn't found for ARM64.
sudo -u class-management python3 -m venv .venv
sudo -u class-management .venv/bin/pip install --upgrade pip
sudo -u class-management .venv/bin/pip install --prefer-binary -r requirements.txt

# .env (note ROOT_PATH and SERVE_FRONTEND):
sudo -u class-management cp .env.example .env
sudo -u class-management $EDITOR .env
```

In `.env` set:

```
DUCKDB_FILE=data/tutorial_center.duckdb
GOOGLE_SERVICE_ACCOUNT_FILE=secrets/service_account.json
GOOGLE_CALENDAR_ID=...
GOOGLE_SHEETS_SPREADSHEET_ID=...
TIMEZONE=Europe/London
LOG_LEVEL=INFO

# Integrated layout: FastAPI serves both UI and API at /class_management
ROOT_PATH=/class_management
SERVE_FRONTEND=true

# Recommended even on home Pi:
API_BEARER_TOKEN=<long-random-string>
```

Drop the Google service-account JSON in `/opt/class_management/secrets/`
and the DuckDB in `/opt/class_management/data/` (scp from your laptop,
or `python -m scripts.download_sheet_to_db`).

## 5. systemd unit (Pi version)

The unit file in `deploy/class-management.service` works on the Pi
unchanged. Install it:

```bash
sudo cp /opt/class_management/deploy/class-management.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now class-management
sudo systemctl status class-management --no-pager
```

Smoke check on the Pi itself:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok","db":"ok","calendar_configured":true}
```

Then from another machine on your LAN (e.g. your laptop):

```bash
curl -s http://192.168.1.50:8000/health
```

If that works, you're done with the Pi side — the rest is networking.

## 6. Port-forward on your router

Goal: requests from the public internet to your home IP get forwarded
to the Pi.

Log into your router admin page. Find **Port Forwarding** /
**Virtual Server** / **NAT** section. Add a rule:

| Field            | Value                          |
| ---------------- | ------------------------------ |
| External port    | `8000` (or `80` — see below)   |
| Internal IP      | `192.168.1.50` (your Pi)       |
| Internal port    | `8000`                         |
| Protocol         | TCP                            |
| Name / comment   | "tutorial center"              |

**Why port 8000 not port 80?** Port 80 is reserved/blessed by browsers
for HTTP and doesn't need to be typed in URLs. To bind to port 80 on
the Pi, uvicorn would need to run as root, or you'd need to put Caddy
or nginx in front (which is the recommended thing — see step 7). For
**now**, forwarding port 8000 keeps the setup simple: people just visit
`http://your-ip:8000/class_management/`.

## 7. Check it's actually reachable

This is where home self-hosts most often fail. Two things to verify:

**(a) Your ISP isn't CGNAT-ing you.** On the Pi:

```bash
curl -s https://api.ipify.org
```

Then open your router admin page → look at the "WAN" / "Internet" IP.

- **They match** → you have a public IP. Proceed.
- **They differ** → you're behind ISP CGNAT. Bare-IP self-hosting from
  home is impossible. Switch to a tunnel (Cloudflare Tunnel) or ask
  your ISP for a public-IP plan (some charge extra, some give it for
  free on request).

**(b) The port is actually open.** From your phone on **mobile data**
(not Wi-Fi — Wi-Fi would loop back through your home network):

```
http://<your-public-ip>:8000/class_management/
```

If it works → done.
If it times out → router rule didn't take, or your ISP blocks port
8000. Try the rule on port 80 instead, or try
<https://www.yougetsignal.com/tools/open-ports/> to verify the port is
reachable.

## 8. (Recommended) Free dynamic DNS so the URL doesn't change

Your home public IP changes whenever the ISP feels like it. Three
minutes of setup gets you a permanent name:

1. Sign up at <https://www.duckdns.org/> (free, log in with GitHub).
2. Pick a subdomain, e.g. `tutorialpi.duckdns.org`. You'll get a token.
3. On the Pi:
   ```bash
   sudo apt install -y curl
   mkdir -p ~/duckdns && cd ~/duckdns
   echo 'echo url="https://www.duckdns.org/update?domains=tutorialpi&token=YOUR-TOKEN&ip=" | curl -k -o ~/duckdns/duck.log -K -' > duck.sh
   chmod 700 duck.sh
   (crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
   ./duck.sh
   ```
4. Visit `http://tutorialpi.duckdns.org:8000/class_management/` —
   resolves to your home IP, automatically tracking changes.

## 9. (Optional) Free HTTPS via Caddy

Once you have a DuckDNS hostname, Caddy can grab a Let's Encrypt cert
for it. You'd:

1. Forward port **80** *and* **443** on the router to the Pi.
2. Install Caddy on the Pi:
   ```bash
   sudo apt install -y caddy
   sudo install -m 644 /opt/class_management/deploy/Caddyfile /etc/caddy/Caddyfile
   sudo $EDITOR /etc/caddy/Caddyfile        # replace test.com with tutorialpi.duckdns.org
   sudo systemctl reload caddy
   ```
3. Stop the port-8000 forward — visitors now use
   `https://tutorialpi.duckdns.org/class_management/`.

This is exactly the [`DEPLOY.md`](DEPLOY.md) flow from step 10
onwards.

## Day-to-day on the Pi

```bash
sudo systemctl status class-management        # is it up?
sudo journalctl -u class-management -f        # tail logs
sudo systemctl restart class-management       # after a change

# Updates:
sudo -u class-management git -C /opt/class_management pull
sudo -u class-management /opt/class_management/.venv/bin/pip install -r /opt/class_management/requirements.txt
sudo systemctl restart class-management

# Pi housekeeping:
sudo apt update && sudo apt upgrade -y         # do this monthly
df -h                                          # check the SD card isn't full
```

## Caveats specific to the Pi

- **SD card wear**: SD cards die after a few years of constant writes.
  Move heavy-write directories to a USB SSD if you'll run this for
  years, or just keep the DuckDB backed up (rsync to your laptop
  weekly).
- **Power cuts** are the #1 way a Pi corrupts its SD card. Consider
  picking up a small UPS HAT if you're going to leave it as a real
  service.
- **Heat**: under sustained load the Pi 4/5 throttles without a heat
  sink. Cheap aluminium case with passive cooling is enough.
- **Bandwidth caps**: most UK home broadband is uncapped, but check
  with your ISP if you'll have many users.

## When to give up and use a tunnel

If any of the following are true, give up on port-forwarding and use
**Cloudflare Tunnel** instead (it sidesteps all home-network issues
and gives you free HTTPS):

- You're on CGNAT (see step 7a).
- Your ISP blocks inbound ports 80/443/8000.
- Your router admin is locked down (student halls, dorm networks).
- The IP changes daily and DuckDNS isn't keeping up.

Run on the Pi:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared
chmod +x cloudflared
./cloudflared tunnel --url http://localhost:8000
```

It prints a `https://random-words.trycloudflare.com` URL that proxies
into your Pi. No router config, no DNS, no certs to manage. Permanent
URL if you sign up.
