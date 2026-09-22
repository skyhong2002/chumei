"""Retired Chrome/Keychain cookie importer; current IG collection uses Apify.

Kept as an explicit failure for old operator commands. This entrypoint does not
read browser credentials, update external RSSHub configuration, or run Docker.
"""

import sys


def main():
    sys.exit(
        "refresh_ig_cookie.py 已停用：本站不再讀取 Chrome／Keychain cookie。"
        "目前 IG 抓取使用 Apify，請依 docs/source-health.md 檢查來源與額度。"
    )


if __name__ == "__main__":
    main()
