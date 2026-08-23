"""Live inventory of COV hosts discovered on 2026-08-23.

Secrets stay on the hosts. This file has only addresses, units and public URLs.
"""

from __future__ import annotations

CURSORDEV = {
    "id": "cursordev",
    "title": "Cursordev · бастион",
    "role": "jump / git mirrors / SSH keys",
    "host": "195.209.219.8",
    "user": "ubuntu",
    "key": "/home/ubuntu/.ssh/id_hosting_1117792",
    "cpu": 8,
    "ram_gb": 32,
    "disk_gb": 300,
}

PROJECTS = [
    {
        "id": "x5",
        "title": "Пятёрочка",
        "short": "X5 / COV",
        "host": "195.209.213.214",
        "user": "ubuntu",
        "key": "/home/ubuntu/.ssh/x5_1070090.pem",
        "root": "/opt/max-chat-collector",
        "env_path": "/opt/max-chat-collector/.env",
        "cpu": 4,
        "ram_gb": 8,
        "disk_gb": 75,
        "extra_disks": ["/mnt/foto-x5"],
        "max_bot_name": "Aiktor",
        "max_bot_username": "id261019082010_bot",
        "max_bot_user_id": 334567774,
        "llm_model": "gpt-4o-mini",
        "llm_base": "https://openai.api.proxyapi.ru/v1",
        "core_units": [
            "max-chat-collector.service",
            "max-collector-dashboard.service",
            "max-mail-idle.service",
            "company-mail-dashboard.service",
            "survey-server.service",
            "nginx.service",
        ],
        "watch_units": [
            "postgresql@16-main.service",
            "github-daily-backup.service",
        ],
        "heal_units": [
            "max-chat-collector.service",
            "max-collector-dashboard.service",
            "max-mail-idle.service",
            "company-mail-dashboard.service",
            "survey-server.service",
            "nginx.service",
        ],
        "http": [
            {"id": "mail", "url": "https://195.209.213.214/", "title": "Почта компании"},
            {"id": "portal", "url": "https://195.209.213.214/max-collector/", "title": "ЦОВ · портал заявок"},
            {"id": "x5mail", "url": "https://195.209.213.214/x5-mail/", "title": "Почта X5"},
        ],
        "notes": [
            "Диск / 79% — /var/lib/max-chat-collector/raw ~27G, photo_reports ~11G, journal ~4G.",
            "github-daily-backup падает: дерево 680MB > лимит 500MB.",
            "Не деплоить на 135 и не запускать deploy-files.ps1 из окна X5.",
        ],
    },
    {
        "id": "chizhik",
        "title": "Чижик",
        "short": "WRS / parallel",
        "host": "195.209.213.135",
        "user": "ubuntu",
        "key": "/home/ubuntu/.ssh/chizhik_1106595.pem",
        "root": "/opt/ie-bot-parallel",
        "env_path": "/opt/ie-bot-parallel/.env",
        "cpu": 4,
        "ram_gb": 8,
        "disk_gb": 75,
        "max_bot_name": "AI бот ЦОВ (Чиж)",
        "max_bot_username": "id2631032431_1_bot",
        "max_bot_user_id": 359698417,
        "llm_model": "gpt-4o-mini",
        "llm_base": "https://api.proxyapi.ru/openai/v1",
        "core_units": [
            "ie-bot-parallel-collector.service",
            "ie-bot-parallel-dashboard.service",
            "ie-bot-parallel-chizhik-dashboard.service",
            "ie-bot-parallel-wrs-report-mail.service",
        ],
        "watch_units": ["postgresql@16-main.service"],
        "heal_units": [
            "ie-bot-parallel-collector.service",
            "ie-bot-parallel-dashboard.service",
            "ie-bot-parallel-chizhik-dashboard.service",
            "ie-bot-parallel-wrs-report-mail.service",
        ],
        "http": [
            {"id": "wrs", "url": "http://195.209.213.135:18083/", "title": "ЦОВ Чижик · портал"},
        ],
        "notes": [
            "Дашборд :18081 только localhost.",
            "platform-api2 на хосте требует сертификат Минцифры (обход: verify=false или api1).",
        ],
    },
    {
        "id": "pm",
        "title": "ПМ",
        "short": "project-manager",
        "host": "195.209.212.218",
        "user": "ubuntu",
        "key": "/home/ubuntu/.ssh/pm_1103179.pem",
        "root": "/opt/project-manager",
        "env_path": "/opt/project-manager/.env",
        "cpu": 2,
        "ram_gb": 4,
        "disk_gb": 37,
        "max_bot_name": "Менеджер проектов ЦОВ",
        "max_bot_username": "id2631032431_bot",
        "max_bot_user_id": 388505246,
        "max_allow_ids": [330798756, 63992802],
        "llm_model": "anthropic/claude-fable-5",
        "llm_fallback": ["anthropic/claude-opus-5", "openai/o3-pro", "openai/gpt-5-pro"],
        "core_units": [
            "project-manager.service",
            "cov-platform.service",
            "ops-desk.service",
            "project-manager-tls.service",
            "project-manager-bitrix.service",
            "project-manager-megaplan.service",
        ],
        "watch_units": [],
        "heal_units": [
            "project-manager.service",
            "cov-platform.service",
            "ops-desk.service",
            "project-manager-tls.service",
            "project-manager-bitrix.service",
            "project-manager-megaplan.service",
        ],
        "http": [
            {"id": "field", "url": "http://195.209.212.218:8096/", "title": "Полевой канон"},
            {"id": "platform", "url": "http://195.209.212.218:8099/", "title": "Платформа Bitrix"},
            {"id": "ops", "url": "http://195.209.212.218:8095/", "title": "Ops Desk сметы"},
            {"id": "tls", "url": "https://195.209.212.218:8443/", "title": "HTTPS полевой"},
        ],
        "notes": [
            "MAX allowlist: Виктор 330798756, Данил 63992802.",
            "Не деплоить collector на 214/135 из окна ПМ.",
        ],
    },
]

SSH_COMMON = [
    "-o",
    "BatchMode=yes",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "ConnectTimeout=12",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ServerAliveInterval=5",
]


def project_by_id(pid: str) -> dict:
    for item in PROJECTS:
        if item["id"] == pid:
            return item
    raise KeyError(pid)


def all_hosts() -> list[dict]:
    hosts = [
        {
            "id": CURSORDEV["id"],
            "title": CURSORDEV["title"],
            "host": CURSORDEV["host"],
            "user": CURSORDEV["user"],
            "key": CURSORDEV["key"],
            "kind": "bastion",
        }
    ]
    for item in PROJECTS:
        hosts.append(
            {
                "id": item["id"],
                "title": item["title"],
                "host": item["host"],
                "user": item["user"],
                "key": item["key"],
                "kind": "prod",
            }
        )
    return hosts
