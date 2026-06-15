# Deploying AlgoBot on a Raspberry Pi

Runs the whole stack in Docker: **Postgres + backend (FastAPI) + nginx (SPA + API proxy)**.

## Requirements
- Raspberry Pi 4 or 5, **2 GB RAM or more**, on **64-bit Raspberry Pi OS** (32-bit needs extra build tools — avoid it).
- Docker + Docker Compose:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER   # then log out/in
  ```

## First run
```bash
git clone <your-repo> algobot && cd algobot

cp .env.prod.example .env
nano .env                       # set passwords + generate secrets (see below)

docker compose -f docker-compose.prod.yml up -d --build
```
Open **http://<pi-ip>:8080** → register → add a Binance account → create a bot.

### Generate the two secrets in `.env`
```bash
# JWT_SECRET
docker run --rm python:3.11-slim python -c "import secrets;print(secrets.token_urlsafe(48))"

# ENCRYPTION_KEY (set once, then BACK IT UP)
docker run --rm python:3.11-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'"
```

## Everyday commands
```bash
docker compose -f docker-compose.prod.yml ps              # status
docker compose -f docker-compose.prod.yml logs -f backend # bot/runner logs
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml down            # stop (keeps data)
```

## Update to a new version
```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## Backups (important)
- **Database**: the `pgdata` Docker volume. Dump it with:
  ```bash
  docker exec algobot-db pg_dump -U algobot algobot > backup.sql
  ```
- **`ENCRYPTION_KEY`**: store it somewhere safe. Lose it → stored Binance secrets become unrecoverable (you'd re-add every account).

## Must-know caveats
- **Single process only.** Don't add `--workers` to uvicorn — bot runners are in-process threads; multiple workers would duplicate every bot and double its orders. (The provided image already runs one process.)
- **Clock must be accurate.** Binance rejects requests if the clock drifts (`-1021 timestamp`). The Pi syncs via NTP by default with internet — verify with `timedatectl`.
- **Auto-resume.** Bots left `enabled` restart trading automatically after a reboot/power blip. Plan for it on real-money accounts.
- **Binance geo-block.** The Pi's IP/jurisdiction must be allowed by Binance, otherwise live trading won't connect.
- **Real money.** Switching an account off testnet trades real funds with real liquidation risk. Test on testnet first.

## Remote access (recommended: VPN, not port-forwarding)
Since this controls API keys, don't expose port 8080 to the internet. Use a mesh VPN:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
Then reach the Pi at `http://<tailscale-ip>:8080` from your devices. For HTTPS, put Caddy in front (auto-TLS) — ask and I'll add it.

## Troubleshooting
- **Frontend build runs out of memory on the Pi** (1 GB models): build the `web` image on a laptop and `docker save`/`load` it, add swap, or ask me to switch to a prebuilt-assets flow.
- **`pip` tries to compile on 32-bit OS**: switch to 64-bit Raspberry Pi OS (wheels exist for aarch64, not armv7).
- **Backend can't reach DB on first boot**: it waits for the db healthcheck; if it still fails, `docker compose ... logs db`.
