import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime


# ========= 从环境变量里读配置（GitHub Secrets 会传进来） =========
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
TARGET_URL = os.environ["TARGET_URL"]
COOKIE = os.environ.get("COOKIE", "")  # 形如 "a=1; b=2"
# =============================================================


def parse_cookies(cookie_str: str):
    """
    把 "a=1; b=2" 这种字符串转成 dict 给 requests 用
    """
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def send_tg_message(text: str):
    """
    发 Telegram 消息
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    r = requests.post(url, data=data, timeout=10)
    r.raise_for_status()


def fetch_stock():
    """
    解析页面上所有 HK 卡片，并提取库存数字。

    你的 HTML 示例：
    <div class="card cartitem shadow w-100">
      ...
      <h4>HK-②</h4>
      ...
      <p class="card-text">库存： 0</p>
      ...
    </div>

    返回值示例：
    {
        "HK-①": 7,
        "HK-②": 0,
        "HK-③": 12
    }
    """

    headers = {
        "User-Agent": "Mozilla/5.0",
    }

    resp = requests.get(
        TARGET_URL,
        headers=headers,
        cookies=parse_cookies(COOKIE),
        timeout=20,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    result = {}

    # 找所有商品卡片
    cards = soup.find_all("div", class_="card cartitem shadow w-100")

    for card in cards:
        # 标题，例如 "HK-②"
        title_tag = card.find("h4")
        if not title_tag:
            continue

        name = title_tag.text.strip()
        if "HK" not in name:
            # 只监控 HK 系列，其它可以忽略
            continue

        # 库存行：<p class="card-text">库存： 0</p>
        stock_tag = card.find("p", class_="card-text")
        if not stock_tag:
            continue

        stock_text = stock_tag.text.strip()
        digits = "".join(ch for ch in stock_text if ch.isdigit())
        if not digits:
            continue

        result[name] = int(digits)

    return result


def format_stock(stock_dict):
    """
    把库存 dict 转成可读文本
    """
    lines = ["📦 IDC 实时库存", ""]
    for k in sorted(stock_dict.keys()):
        lines.append(f"{k}: {stock_dict[k]}")
    lines.append("")
    lines.append(
        "更新时间: "
        + datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    return "\n".join(lines)


def main():
    try:
        stock = fetch_stock()
    except Exception as e:
        # 抓取失败直接通知你
        send_tg_message(f"⚠️ 库存监控抓取失败：{e}")
        return

    if not stock:
        send_tg_message("⚠️ 库存监控没有解析到任何 HK 库存，请检查页面结构或脚本。")
        return

    msg = format_stock(stock)
    send_tg_message(msg)


if __name__ == "__main__":
    main()
