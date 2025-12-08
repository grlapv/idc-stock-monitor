import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime


# ========= 从环境变量里读配置（GitHub Secrets 会传进来） =========
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
TARGET_URL = os.environ["TARGET_URL"]
COOKIE = os.environ.get("COOKIE", "")  # 形如 "a=1; b=2"
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


def escape_md_v2(text: str) -> str:
    """
    Telegram MarkdownV2 需要转义的字符：
    _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special_chars = r"_*[]()~`>#+-=|{}.!"
    for ch in special_chars:
        text = text.replace(ch, "\\" + ch)
    return text


def send_tg_message(text: str):
    """
    发 Telegram 消息（MarkdownV2）
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "MarkdownV2",
    }
    r = requests.post(url, data=payload, timeout=10)
    r.raise_for_status()


def fetch_stock():
    """
    解析页面上的所有卡片，并提取库存数字。

    支持的卡片示例：
    <div class="card cartitem shadow w-100">
      ...
      <h4>HK-②</h4> / <h4>CA</h4> / <h4>DE</h4> / <h4>FR-①</h4> / <h4>FR-②</h4>
      ...
      <p class="card-text">库存： 0</p>
      ...
    </div>

    返回值示例：
    {
        "HK-①": 7,
        "HK-②": 0,
        "HK-③": 12,
        "CA": 0,
        "DE": 0,
        "FR-①": 0,
        "FR-②": 0,
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
        # 标题，例如 "HK-②"、"CA"、"DE"、"FR-①"、"FR-②"
        title_tag = card.find("h4")
        if not title_tag:
            continue

        name = title_tag.text.strip()

        # 只关心 HK / CA / DE / FR 这些区域
        if not any(prefix in name for prefix in ["HK", "CA", "DE", "FR"]):
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


def build_message(stock_dict, mode: str) -> str:
    """
    根据模式生成 MarkdownV2 文本
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

    # 排序一下，避免顺序乱
    hk = dict(sorted(hk.items(), key=lambda x: x[0]))
    other = dict(sorted(other.items(), key=lambda x: x[0]))

    if mode == "daily":
        title = "📊 IDC 每日库存汇总"
    else:
        title = "⏱ IDC 实时库存"

    lines = [escape_md_v2(title), ""]

    # HK 区（避孕套）
    if hk:
        lines.append(escape_md_v2("【HK 区 \\(避孕套\\)】"))
        for k, v in hk.items():
            # 给一点简单状态提示：0 = 售罄；>0 = 有货
            if v == 0:
                status = "售罄"
                icon = "❌"
            else:
                status = "有货"
                icon = "✅"
            line = f"{k}：{v} \\({status}{icon}\\)"
            lines.append(escape_md_v2(line))
        lines.append("")

    # 其他区（避孕药）
    if other:
        lines.append(escape_md_v2("【其他区 \\(避孕药\\)】"))
        for k, v in other.items():
            if v == 0:
                status = "售罄"
                icon = "❌"
            else:
                status = "有货"
                icon = "✅"
            line = f"{k}：{v} \\({status}{icon}\\)"
            lines.append(escape_md_v2(line))
        lines.append("")

    footer = f"更新时间：{now_utc}"
    lines.append(escape_md_v2(footer))

    return "\n".join(lines)


def main():
    try:
        stock = fetch_stock()
    except Exception as e:
        # 抓取失败直接通知你
        msg = f"⚠️ 库存监控抓取失败：{e}"
        send_tg_message(escape_md_v2(msg))
        return

    if not stock:
        msg = "⚠️ 库存监控没有解析到任何库存，请检查页面结构或脚本。"
        send_tg_message(escape_md_v2(msg))
        return

    text = build_message(stock, MODE)
    send_tg_message(text)


if __name__ == "__main__":
    main()
