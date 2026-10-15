# 🚀 CommitCast

A high-performance, asynchronous Telegram bot built with **Pyrogram** and **Motor (MongoDB)** for real-time GitHub commit tracking, Pull Request & Issue alerts, CI/CD pipeline notifications, release broadcasts, community changelogs, and direct two-way issue management.

---

## ✨ Features

- **⚡ Real-time GitHub Polling & Webhook Support**:
  - Monitors repositories for commits, pull requests, issues, releases, GitHub Actions runs, and star/fork events.
  - Supports both background polling and high-throughput webhook delivery.
- **📢 Intelligent Destination Routing**:
  - Directs high-volume commit logs to dedicated log channels.
  - Keeps community groups clean with selective PR, Issue, and Release routing.
  - Supports private DM delivery mode for confidential repositories.
- **⚙️ GitHub Actions / CI/CD Alerts**:
  - 🟢 **Succeeded**: Workflow run passed.
  - 🔴 **Failed**: Workflow run failed or timed out.
  - 🟡 **Approval Required**: Waiting for manual reviewer approval.
  - Direct links to workflow runs, triggering commits, and actors.
- **🚀 Release & Tag Broadcasts**:
  - Automatically announces new releases and published tags.
  - Parses and formats release markdown changelogs directly into Telegram HTML.
- **🛠️ Direct Issue & PR Commands**:
  - `/close <#number> [comment]` — Close an issue or PR.
  - `/reopen <#number> [comment]` — Reopen an issue or PR.
  - `/label <#number> <labels>` — Add labels to an issue or PR.
  - Works via direct commands or simply replying to any alert message!
- **⭐ Star & Fork Notifications**:
  - Real-time alerts when users star or fork your repository, with profile links and counts.
- **💬 Direct Telegram-to-GitHub Reply Bridge**:
  - Reply to any commit, PR, or issue alert in Telegram to post authentic comments directly on GitHub via your connected GitHub account.
- **⏳ Automatic Group Alert Purging (24h)**:
  - Automatically purges PR and Issue alerts from connected groups after 24 hours to keep chats tidy.
- **🖼️ Monthly Banner Management**:
  - Upload, preview, and attach custom monthly banners to release announcements.
- **📝 Automated Rich Changelogs**:
  - Generates comprehensive 15-day and 30-day release summaries categorized into Features, Improvements, and Maintenance.
- **🔘 Interactive Dashboard (`/repos`)**:
  - Per-repository toggles for Commits, Issues & PRs, Releases, CI/CD Workflows, and Stars/Forks.

---

## 📁 Project Architecture

```
CommitCast/
├── app/
│   ├── handlers/
│   │   ├── bot_handlers.py             # General commands (/start, /help, channel management)
│   │   ├── issue_cmd_handlers.py       # Issue & PR commands (/close, /reopen, /label)
│   │   ├── release_handlers.py         # Changelog drafting and preview
│   │   ├── repo_manager_handlers.py    # Repository control panel & toggles (/repos)
│   │   ├── reply_handlers.py           # Reply-to-comment GitHub bridge
│   │   └── keyboards.py                # Inline markup and rich button builder
│   ├── services/
│   │   ├── github_api.py               # GitHub REST API client
│   │   ├── github_poller.py            # Polling loop for commits, issues, CI/CD, releases, stars
│   │   └── webhook_server.py           # FastAPI webhook listener
│   ├── core/
│   │   ├── config.py                   # Pydantic environment configuration
│   │   ├── logging_config.py           # Logging setup
│   │   └── constants.py                # Application constants & emoji codes
│   ├── database/
│   │   ├── database.py                 # MongoDB AsyncIOMotorClient database manager
│   │   └── repositories.py             # Repository data access abstractions
│   └── utils/
│       ├── changelog.py                # Natural changelog parsing & grouping
│       ├── formatters.py               # Telegram HTML formatters & markdown converter
│       └── validators.py               # Input validation routines
├── scripts/
│   └── verify_setup.py                 # Environment verification script
├── data/                               # Local data files
├── main.py                             # Application entry point
├── .env.example                        # Example environment variables
├── .gitignore                          # Secrets, sessions, and cache exclusion
├── requirements.txt                    # Python dependencies
├── Dockerfile                          # Container deployment definition
├── docker-compose.yml                  # Multi-service container orchestration
└── README.md                           # Documentation
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- Python 3.10+
- MongoDB instance (local or MongoDB Atlas)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Telegram API ID and Hash from [my.telegram.org](https://my.telegram.org)

### 2. Clone and Setup Environment
```bash
git clone https://github.com/VeezNetworks/CommitCast.git
cd CommitCast

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials:
```env
# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH="your_telegram_api_hash"

# Database Configuration (MongoDB)
MONGODB_URI="mongodb://localhost:27017"
DATABASE_NAME="commitcast_bot"

# Polling Interval (in seconds)
POLL_INTERVAL_SECONDS=15

# Developer & Owner Settings
DEVELOPER_OWNER_ID=123456789
GITHUB_TOKEN=""
GITHUB_CLIENT_ID="your_github_oauth_client_id"
GITHUB_WEBHOOK_SECRET=""
```

### 4. Verify Setup & Run
```bash
# Verify environment and database connection
python scripts/verify_setup.py

# Launch the bot
python main.py
```

---

## 🐳 Docker Deployment

### Run with Docker Compose
```bash
docker compose up -d --build
```
This launches both the **MongoDB** database service and the **CommitCast** container automatically.

---

## 📄 License
MIT License. Free for open-source and commercial use.
