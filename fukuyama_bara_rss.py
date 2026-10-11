import requests
import hashlib
import re
import time
import xml.etree.ElementTree as ET

from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime


SOURCE_URL = "https://www.fc-hosp.jp/soshiki/5/7385.html"
OUTPUT = Path(__file__).parent / "fukuyama_bara.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}


# --------------------------------------------------
# 既存RSS読み込み
# --------------------------------------------------

old_items = {}

if OUTPUT.exists():

    try:
        tree = ET.parse(OUTPUT)

        for item in tree.getroot().findall("./channel/item"):

            guid = item.findtext("guid", "")

            if guid:
                old_items[guid] = {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "description": item.findtext(
                        "description", ""
                    ),
                    "pubDate": item.findtext(
                        "pubDate", ""
                    ),
                    "guid": guid,
                }

    except Exception as e:

        print("既存RSS読み込みエラー:", e)
        print("安全のため今回は更新しません。")

        raise SystemExit(0)


print("既存RSS件数:", len(old_items))


# --------------------------------------------------
# ページ取得
# --------------------------------------------------

response = None
MAX_RETRIES = 3

for attempt in range(1, MAX_RETRIES + 1):

    try:

        print(
            f"広報誌ばらページ取得 "
            f"{attempt}/{MAX_RETRIES}"
        )

        response = requests.get(
            SOURCE_URL,
            headers=HEADERS,
            timeout=30
        )

        print("HTTP:", response.status_code)

        response.raise_for_status()
        break

    except requests.RequestException as e:

        print("取得失敗:", e)
        response = None

        if attempt < MAX_RETRIES:
            print("10秒待って再試行します。")
            time.sleep(10)


if response is None:

    print()
    print("ページを取得できませんでした。")
    print("今回はRSSを更新しません。")
    print("既存XMLをそのまま維持します。")

    raise SystemExit(0)


# --------------------------------------------------
# HTML解析
# --------------------------------------------------

soup = BeautifulSoup(
    response.content,
    "html.parser"
)

main = soup.select_one(
    "div.detail_free"
)

if not main:

    print("本文領域を取得できませんでした。")
    print("既存XMLを維持します。")

    raise SystemExit(0)


# --------------------------------------------------
# 「広報誌ばら」の号数・年月を取得
# --------------------------------------------------

text = main.get_text(
    " ",
    strip=True
)

issue_pattern = re.compile(
    r"広報誌(?:ばら)?(?:第)?"
    r"(\d+)号"
    r"（"
    r"(20\d{2})年"
    r"(\d{1,2})月"
    r"）"
)

matches = list(
    issue_pattern.finditer(text)
)


# --------------------------------------------------
# PDF取得
# --------------------------------------------------

pdf_links = []

for a in main.find_all(
    "a",
    href=True
):

    href = a["href"]

    if ".pdf" not in href.lower():
        continue

    link = urljoin(
        SOURCE_URL,
        href
    )

    if link not in pdf_links:
        pdf_links.append(link)


print()
print(
    "広報誌の号数取得:",
    len(matches),
    "件"
)

print(
    "ページ内PDF:",
    len(pdf_links),
    "件"
)


# --------------------------------------------------
# 安全確認
# --------------------------------------------------

if len(matches) == 0:

    print("広報誌ばらの号数を取得できませんでした。")
    print("ページ構造変更の可能性があります。")
    print("既存XMLを維持します。")

    raise SystemExit(0)


if len(pdf_links) < len(matches):

    print("PDF数が広報誌の号数より少なくなっています。")
    print("ページ構造変更の可能性があります。")
    print("既存XMLを維持します。")

    raise SystemExit(0)


# --------------------------------------------------
# 現在掲載されている広報誌を作成
#
# 現在のページでは、
# 広報誌の各号 → PDF
# の順序が一致している
# --------------------------------------------------

current_items = []

for i, match in enumerate(matches):

    number = int(
        match.group(1)
    )

    year = int(
        match.group(2)
    )

    month = int(
        match.group(3)
    )

    link = pdf_links[i]

    title = (
        f"福山市民病院 広報誌ばら "
        f"{number}号（{year}年{month}月）"
    )

    # 発行月の1日をRSS上の日付にする
    dt = datetime(
        year,
        month,
        1,
        12,
        0,
        0,
        tzinfo=JST
    )

    guid = hashlib.sha256(
        link.encode("utf-8")
    ).hexdigest()

    current_items.append({
        "title": title,
        "link": link,
        "description": (
            f"福山市民病院 広報誌ばら "
            f"{number}号（{year}年{month}月）"
        ),
        "pubDate": format_datetime(dt),
        "guid": guid,
    })


print()
print(
    "今回取得:",
    len(current_items),
    "件"
)


# --------------------------------------------------
# 既存RSSと統合
# --------------------------------------------------

all_items = []
seen_guids = set()


for item in current_items:

    if item["guid"] not in seen_guids:

        all_items.append(item)
        seen_guids.add(
            item["guid"]
        )


for guid, item in old_items.items():

    if guid not in seen_guids:

        all_items.append(item)
        seen_guids.add(guid)


# --------------------------------------------------
# 新しい順
# --------------------------------------------------

def get_date(item):

    try:
        return parsedate_to_datetime(
            item["pubDate"]
        )

    except Exception:

        return datetime.min.replace(
            tzinfo=timezone.utc
        )


all_items.sort(
    key=get_date,
    reverse=True
)


# --------------------------------------------------
# RSS生成
# --------------------------------------------------

rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)

ET.SubElement(
    channel,
    "title"
).text = "福山市民病院 広報誌ばら"

ET.SubElement(
    channel,
    "link"
).text = SOURCE_URL

ET.SubElement(
    channel,
    "description"
).text = (
    "福山市民病院 広報誌ばら 更新情報"
)

ET.SubElement(
    channel,
    "language"
).text = "ja"


for item in all_items:

    element = ET.SubElement(
        channel,
        "item"
    )

    ET.SubElement(
        element,
        "title"
    ).text = item["title"]

    ET.SubElement(
        element,
        "link"
    ).text = item["link"]

    ET.SubElement(
        element,
        "description"
    ).text = item["description"]

    ET.SubElement(
        element,
        "pubDate"
    ).text = item["pubDate"]

    guid_element = ET.SubElement(
        element,
        "guid"
    )

    guid_element.set(
        "isPermaLink",
        "false"
    )

    guid_element.text = item["guid"]


# --------------------------------------------------
# XML保存
# --------------------------------------------------

tree = ET.ElementTree(rss)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)


print()
print("RSS作成成功")

print(
    "RSS保存件数:",
    len(all_items),
    "件"
)

print(
    "保存先:",
    OUTPUT
)

print()
print("今回取得した広報誌:")

for i, item in enumerate(
    current_items,
    start=1
):

    print()
    print(
        f"[{i}] "
        f"{item['title']}"
    )

    print(
        "    ",
        item["link"]
    )