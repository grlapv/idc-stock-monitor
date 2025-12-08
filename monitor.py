import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime


# ========= 从环境变量里读配置（GitHub Secrets 会传进来） =========
# 支持多个 URL，用逗号分隔：URL1,URL2,URL3...
RAW_TARGET_URL = os.environ["TARGET_URL"]
COOKIE = os.environ.get("COOKIE", "")  # 形如 "a=1; b=2"
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
MODE = os.environ.get("MODE", "realtime")  # realtime / daily
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
    发 Telegram 消息（纯文本，不用 Markdown，避免 400 错误）
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
    }
    r = requests.post(url, data=data, timeout=10)
    r.raise_for_status()


def fetch_stock_from_url(url: str):
    """
    从单个 URL 解析库存，返回 dict
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
    }

    resp = requests.get(
        url,
        headers=headers,
        cookies=parse_cookies(COOKIE),
        timeout=20,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    result = {}

    # 所有商品卡片：class 里同时有 card 和 cartitem 就行
    cards = soup.select("div.card.cartitem")

    for card in cards:
        # 标题，例如 "HK-②"、"CA"、"DE"、"FR-①"、"FR-②"
        title_tag = card.find("h4")
        if not title_tag:
            continue

        name = title_tag.get_text(strip=True)

        # 只关心 HK / CA / DE / FR 这些区域
        if not any(prefix in name for prefix in ["HK", "CA", "DE", "FR"]):
            continue

        # 页面里可能有多个 p.card-text，我们要找包含“库存”的那个
        stock_tag = None
        for p in card.find_all("p", class_="card-text"):
            if "库存" in p.get_text():
                stock_tag = p
                break

        if not stock_tag:
            continue

        stock_text = stock_tag.get_text(strip=True)
        digits = "".join(ch for ch in stock_text if ch.isdigit())
        if not digits:
            continue

        result[name] = int(digits)

    return result


def fetch_stock():
    """
    支持多个页面：把所有 URL 的库存合并到一个 dict
    """
    # 支持 TARGET_URL 填多个，用逗号分隔
    urls = [u.strip() for u in RAW_TARGET_URL.split(",") if u.strip()]

    total = {}
    for url in urls:
        part = fetch_stock_from_url(url)
        # 后面的页面如果有同名（比如同一个地区在不同套餐里），以最后一个为准
        total.update(part)

    return total


def build_message(stock_dict, mode: str) -> str:
    """
    根据模式生成文本
    mode: "realtime" 实时；"daily" 每日汇总
    """

    now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # 分组
    hk = {}
    other = {}
    for k, v in stock_dict.items():
        if k.startswith("HK"):
            hk[k] = v
        else:
            other[k] = v

    hk = dict(sorted(hk.items(), key=lambda x: x[0]))
    other = dict(sorted(other.items(), key=lambda x: x[0]))

    if mode == "daily":
        title = "📊 IDC 每日库存汇总"
    else:
        title = "⏱ IDC 实时库存"

    lines = [title, ""]

    # HK 区（避孕套）
    if hk:
        lines.append("【HK 区（避孕套）】")
        for k, v in hk.items():
            if v == 0:
                status = "售罄 ❌"
            else:
                status = "有货 ✅"
            lines.append(f"{k}: {v}（{status}）")
        lines.append("")

    # 其他区（避孕药）
    if other:
        lines.append("【其他区（避孕药）】")
        for k, v in other.items():
            if v == 0:
                status = "售罄 ❌"
            else:
                status = "有货 ✅"
            lines.append(f"{k}: {v}（{status}）")
        lines.append("")

    lines.append(f"更新时间：{now_utc}")

    return "\n".join(lines)


def main():
    try:
        stock = fetch_stock()
    except Exception as e:
        msg = f"⚠️ 库存监控抓取失败：{e}"
        send_tg_message(msg)
        return

    if not stock:
        msg = "⚠️ 库存监控没有解析到任何库存，请检查页面结构或脚本。"
        send_tg_message(msg)
        return

    text = build_message(stock, MODE)
    send_tg_message(text)


if __name__ == "__main__":
    main()
