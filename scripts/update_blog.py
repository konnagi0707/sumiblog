#!/usr/bin/env python3
"""Build and update the Miyachi Sumire official blog archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from lxml import html


BASE_URL = "https://www.hinatazaka46.com"
MEMBER_ID = "34"
MEMBER_NAME = "\u5bae\u5730 \u3059\u307f\u308c"
MEMBER_TAG = "\u5bae\u5730\u3059\u307f\u308c"
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
POSTS_PATH = DATA_DIR / "posts.json"
META_PATH = DATA_DIR / "archive_meta.json"
MEMBER_PATH = DATA_DIR / "member.json"
MEMBER_HISTORY_PATH = DATA_DIR / "member_history.json"
IMAGES_DIR = DATA_DIR / "images"
MEMBER_DIR = DATA_DIR / "member"
PROFILE_ARCHIVE_DIR = MEMBER_DIR / "archive" / "profile"
GREETING_CARD_ARCHIVE_DIR = MEMBER_DIR / "archive" / "greeting_card"
GREETING_PHOTO_ARCHIVE_DIR = MEMBER_DIR / "archive" / "greeting_photo"
REQUEST_DELAY_SECONDS = 0.25
JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class PostLink:
    post_id: int
    url: str


def log(message: str) -> None:
    print(message, flush=True)


def ensure_dirs() -> None:
    for directory in [
        DATA_DIR,
        IMAGES_DIR,
        MEMBER_DIR,
        PROFILE_ARCHIVE_DIR,
        GREETING_CARD_ARCHIVE_DIR,
        GREETING_PHOTO_ARCHIVE_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_jst_month() -> str:
    return datetime.now(JST).strftime("%Y-%m")


def request_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=40)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def request_bytes(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def normalize_url(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        return ""
    return urljoin(BASE_URL, url)


def local_path_for_json(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    cleaned = cleaned.strip(" .")
    return cleaned or "image"


def image_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return suffix
    return ".jpg"


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def archive_filename(prefix: str, original_url: str) -> str:
    parsed_name = safe_filename(Path(urlparse(original_url).path).name)
    if "." not in parsed_name:
        parsed_name += image_extension(original_url)
    return f"{prefix}_{short_hash(original_url)}_{parsed_name}"


def download_image(
    session: requests.Session,
    original_url: str,
    destination: Path,
    *,
    force: bool = False,
) -> str:
    if not original_url:
        return ""

    if destination.exists() and destination.stat().st_size > 0 and not force:
        return local_path_for_json(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(request_bytes(session, original_url))
    return local_path_for_json(destination)


def parse_post_id_from_href(href: str) -> int | None:
    match = re.search(r"/diary/detail/(\d+)", href or "")
    if not match:
        return None
    return int(match.group(1))


def collect_post_links(session: requests.Session, max_pages: int | None = None) -> list[PostLink]:
    links: list[PostLink] = []
    seen: set[int] = set()
    page = 0

    while True:
        if max_pages is not None and page >= max_pages:
            break

        url = (
            f"{BASE_URL}/s/official/diary/member/list?ima=0000&ct={MEMBER_ID}&cd=member"
            + (f"&page={page}" if page else "")
        )
        tree = html.fromstring(request_text(session, url))
        articles = tree.xpath(
            '//div[contains(concat(" ", normalize-space(@class), " "), " p-blog-article ")]'
        )

        page_links: list[PostLink] = []
        for article in articles:
            hrefs = article.xpath(
                './/a[contains(concat(" ", normalize-space(@class), " "), " c-button-blog-detail ")]/@href'
            )
            if not hrefs:
                continue
            post_id = parse_post_id_from_href(hrefs[0])
            if post_id is None or post_id in seen:
                continue
            seen.add(post_id)
            page_links.append(PostLink(post_id, normalize_url(hrefs[0])))

        if not page_links:
            break

        links.extend(page_links)
        log(f"page {page + 1}: {len(page_links)} posts")
        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    return links


def parse_title(tree: html.HtmlElement) -> str:
    candidates = [
        *tree.xpath(
            '//*[contains(concat(" ", normalize-space(@class), " "), " c-blog-article__title ")]//text()'
        ),
        *tree.xpath('//meta[@itemprop="name"]/@content'),
        *tree.xpath('//meta[@property="og:title"]/@content'),
        *tree.xpath("//title/text()"),
    ]
    for candidate in candidates:
        title = str(candidate).strip()
        if not title:
            continue
        title = title.split(" | ")[0].strip()
        title = re.sub(r"\u65e5\u5411\u574246.*$", "", title).strip()
        title = title.removesuffix("\u516c\u5f0f\u30d6\u30ed\u30b0").strip()
        if title and title not in {"|", MEMBER_NAME, MEMBER_TAG}:
            return title
    return "\u7121\u984c"


def parse_date(tree: html.HtmlElement) -> tuple[str, str]:
    text_candidates = tree.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " c-blog-article__date ")]//text()'
    )
    date_text = " ".join(t.strip() for t in text_candidates if t.strip()).strip()
    match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", date_text)
    if not match:
        return "", date_text

    year, month, day, hour, minute = match.groups()
    date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    if hour is None:
        return date, date_text
    return date, f"{date} {int(hour):02d}:{int(minute):02d}"


def append_normalized(parts: list[str], text: str | None) -> None:
    if text:
        parts.append(text.replace("\xa0", " "))


def normalize_text_block(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def flush_text(text_parts: list[str], blocks: list[dict]) -> None:
    text = normalize_text_block("".join(text_parts))
    text_parts.clear()
    if text:
        blocks.append({"type": "text", "text": text})


def walk_content(
    node: html.HtmlElement,
    text_parts: list[str],
    blocks: list[dict],
    image_urls: list[str],
) -> None:
    append_normalized(text_parts, node.text)

    for child in node:
        tag = str(child.tag).lower()

        if tag == "br":
            text_parts.append("\n")
        elif tag == "img":
            flush_text(text_parts, blocks)
            src = normalize_url(child.get("src"))
            if src:
                image_urls.append(src)
                blocks.append({"type": "image", "originalSrc": src})
        elif tag == "a":
            label = normalize_text_block(child.text_content())
            href = normalize_url(child.get("href"))
            if label and href and href not in label:
                append_normalized(text_parts, f"{label} ({href})")
            elif label:
                append_normalized(text_parts, label)
            elif href:
                append_normalized(text_parts, href)
        else:
            walk_content(child, text_parts, blocks, image_urls)

        append_normalized(text_parts, child.tail)


def extract_blocks(tree: html.HtmlElement) -> tuple[list[dict], list[str]]:
    containers = tree.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " c-blog-article__text ")]'
    )
    if not containers:
        return [], []

    blocks: list[dict] = []
    image_urls: list[str] = []
    text_parts: list[str] = []
    walk_content(containers[0], text_parts, blocks, image_urls)
    flush_text(text_parts, blocks)
    return blocks, image_urls


def build_image_blocks(
    session: requests.Session,
    post_id: int,
    blocks: list[dict],
    *,
    download_images: bool,
    force_images: bool,
) -> list[dict]:
    image_index = 0
    result: list[dict] = []

    for block in blocks:
        if block.get("type") != "image":
            result.append(block)
            continue

        image_index += 1
        original_src = str(block.get("originalSrc") or "").strip()
        src = original_src
        if download_images and original_src:
            basename = safe_filename(Path(urlparse(original_src).path).name)
            if "." not in basename:
                basename += image_extension(original_src)
            destination = IMAGES_DIR / str(post_id) / f"{image_index:03d}_{basename}"
            try:
                src = download_image(session, original_src, destination, force=force_images)
            except Exception as exc:
                log(f"warning: failed to download {original_src}: {exc}")

        result.append({"type": "image", "src": src, "originalSrc": original_src})

    return result


def parse_post(
    session: requests.Session,
    link: PostLink,
    *,
    download_images: bool,
    force_images: bool,
) -> dict:
    tree = html.fromstring(request_text(session, link.url))
    title = parse_title(tree) or "\u7121\u984c"
    date, datetime_text = parse_date(tree)
    blocks, image_urls = extract_blocks(tree)
    blocks = build_image_blocks(
        session,
        link.post_id,
        blocks,
        download_images=download_images,
        force_images=force_images,
    )

    content = "\n\n".join(
        block["text"] for block in blocks if block.get("type") == "text" and block.get("text")
    )
    tags = [MEMBER_TAG]
    if date:
        tags.append(date[:7])

    cover = next((block for block in blocks if block.get("type") == "image"), None)
    return {
        "id": link.post_id,
        "title": title,
        "date": date,
        "datetime": datetime_text,
        "tags": tags,
        "content": content,
        "contentBlocks": blocks,
        "imageCount": len(image_urls),
        "cover": cover.get("src") if cover else "",
        "sourceUrl": link.url,
    }


def load_existing_posts() -> dict[int, dict]:
    if not POSTS_PATH.exists():
        return {}
    with POSTS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        return {}
    return {
        int(post["id"]): post
        for post in payload
        if isinstance(post, dict) and str(post.get("id", "")).isdigit()
    }


def sort_posts(posts: Iterable[dict]) -> list[dict]:
    return sorted(posts, key=lambda post: (post.get("date") or "", int(post.get("id") or 0)), reverse=True)


def read_json(path: Path, fallback: object) -> object:
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def download_member_current_image(
    session: requests.Session,
    name: str,
    url: str,
    *,
    download_images: bool,
    force_images: bool,
) -> dict:
    if not url:
        return {"src": "", "originalSrc": ""}
    src = url
    if download_images:
        destination = MEMBER_DIR / f"{name}{image_extension(url)}"
        try:
            src = download_image(session, url, destination, force=force_images)
        except Exception as exc:
            log(f"warning: failed to download member image {url}: {exc}")
    return {"src": src, "originalSrc": url}


def parse_member(session: requests.Session, *, download_images: bool, force_images: bool) -> dict:
    source_url = f"{BASE_URL}/s/official/artist/{MEMBER_ID}?ima=0000"
    tree = html.fromstring(request_text(session, source_url))
    raw_image_urls = [
        normalize_url(src)
        for src in tree.xpath("//img/@src")
        if "cdn.hinatazaka46.com/images/14/" in normalize_url(src)
    ]

    profile_url = next((url for url in raw_image_urls if "1000_1000_102400" in url), "")
    greeting_card_url = next(
        (
            url
            for url in raw_image_urls
            if url != profile_url and "-01." not in Path(urlparse(url).path).name
        ),
        "",
    )
    greeting_photo_url = next(
        (url for url in raw_image_urls if "-01." in Path(urlparse(url).path).name),
        "",
    )

    return {
        "id": int(MEMBER_ID),
        "name": MEMBER_NAME,
        "kana": "\u307f\u3084\u3061 \u3059\u307f\u308c",
        "roman": "SUMIRE MIYACHI",
        "sourceUrl": source_url,
        "greetingListUrl": f"{BASE_URL}/s/official/page/greeting?ima=0000",
        "attributes": [
            {"label": "\u751f\u5e74\u6708\u65e5", "value": "2005\u5e7412\u670831\u65e5"},
            {"label": "\u661f\u5ea7", "value": "\u3084\u304e\u5ea7"},
            {"label": "\u8eab\u9577", "value": "165cm"},
            {"label": "\u51fa\u8eab\u5730", "value": "\u795e\u5948\u5ddd\u770c"},
            {"label": "\u8840\u6db2\u578b", "value": "\u4e0d\u660e"},
        ],
        "images": {
            "profile": download_member_current_image(
                session,
                "profile",
                profile_url,
                download_images=download_images,
                force_images=force_images,
            ),
            "greetingCard": download_member_current_image(
                session,
                "greeting_card",
                greeting_card_url,
                download_images=download_images,
                force_images=force_images,
            ),
            "greetingPhoto": download_member_current_image(
                session,
                "greeting_photo",
                greeting_photo_url,
                download_images=download_images,
                force_images=force_images,
            ),
        },
        "updatedAt": utc_now_iso(),
    }


def load_member_history() -> dict:
    fallback = {"version": 1, "updatedAt": "", "profileHistory": [], "greetingHistory": []}
    payload = read_json(MEMBER_HISTORY_PATH, fallback)
    if not isinstance(payload, dict):
        return fallback
    payload.setdefault("version", 1)
    payload.setdefault("updatedAt", "")
    payload.setdefault("profileHistory", [])
    payload.setdefault("greetingHistory", [])
    return payload


def archive_member_image(
    session: requests.Session,
    original_url: str,
    archive_dir: Path,
    prefix: str,
    *,
    download_images: bool,
    force_images: bool,
) -> dict:
    if not original_url:
        return {"src": "", "originalSrc": ""}
    src = original_url
    if download_images:
        destination = archive_dir / archive_filename(prefix, original_url)
        try:
            src = download_image(session, original_url, destination, force=force_images)
        except Exception as exc:
            log(f"warning: failed to archive member image {original_url}: {exc}")
    return {"src": src, "originalSrc": original_url}


def archive_member_image_or_empty(
    session: requests.Session,
    original_url: str,
    archive_dir: Path,
    prefix: str,
    *,
    download_images: bool,
    force_images: bool,
) -> dict:
    if not original_url:
        return {"src": "", "originalSrc": ""}
    try:
        return archive_member_image(
            session,
            original_url,
            archive_dir,
            prefix,
            download_images=download_images,
            force_images=force_images,
        )
    except Exception as exc:
        log(f"warning: failed to archive {original_url}: {exc}")
        return {"src": "", "originalSrc": ""}


def timestamp_to_jst_month(timestamp: str) -> str:
    try:
        captured_at = datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return timestamp[:4] + "-" + timestamp[4:6]
    return captured_at.astimezone(JST).strftime("%Y-%m")


def timestamp_to_iso(timestamp: str) -> str:
    try:
        captured_at = datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return utc_now_iso()
    return captured_at.isoformat()


def fetch_cdx_snapshots(session: requests.Session, url_pattern: str) -> list[dict]:
    cdx_url = (
        "https://web.archive.org/cdx/search/cdx"
        f"?url={url_pattern}"
        "&output=json"
        "&fl=timestamp,original,statuscode,mimetype,digest"
        "&filter=statuscode:200"
        "&collapse=digest"
        "&from=202211"
    )
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = session.get(cdx_url, timeout=120)
            response.raise_for_status()
            break
        except Exception as exc:
            last_error = exc
            if attempt == 3:
                raise
            time.sleep(2 * attempt)
    else:
        raise last_error or RuntimeError("CDX request failed")

    rows = response.json()
    if not isinstance(rows, list) or len(rows) <= 1:
        return []
    headers = rows[0]
    snapshots = [dict(zip(headers, row)) for row in rows[1:]]
    return sorted(
        (
            snapshot
            for snapshot in snapshots
            if str(snapshot.get("mimetype", "")).startswith("text/html")
        ),
        key=lambda snapshot: str(snapshot.get("timestamp", "")),
    )


def archived_snapshot_url(snapshot: dict) -> str:
    timestamp = snapshot.get("timestamp", "")
    original = snapshot.get("original", "")
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def extract_background_urls(style_text: str) -> list[str]:
    urls = []
    for match in re.findall(r"url\((['\"]?)(.*?)\1\)", style_text or ""):
        url = normalize_url(match[1])
        if url:
            urls.append(url)
    return urls


def infer_greeting_photo_url(card_url: str) -> str:
    parsed = urlparse(card_url)
    path = parsed.path
    suffix = Path(path).suffix
    if not suffix:
        return ""
    return card_url[: -len(suffix)] + "-01" + suffix


def extract_member_images_from_artist_tree(tree: html.HtmlElement) -> dict:
    raw_image_urls = [
        normalize_url(src)
        for src in tree.xpath("//img/@src")
        if "hinatazaka46.com/images/14/" in normalize_url(src)
    ]
    style_image_urls = []
    for style in tree.xpath("//*[@style]/@style"):
        style_image_urls.extend(
            url for url in extract_background_urls(style) if "hinatazaka46.com/images/14/" in url
        )
    image_urls = raw_image_urls + style_image_urls

    profile_url = next((url for url in image_urls if "1000_1000_102400" in url), "")
    greeting_card_url = next(
        (
            url
            for url in image_urls
            if url != profile_url and "-01." not in Path(urlparse(url).path).name and "400_320_102400" not in url
        ),
        "",
    )
    greeting_photo_url = next(
        (url for url in image_urls if "-01." in Path(urlparse(url).path).name),
        "",
    )

    return {
        "profile": profile_url,
        "greetingCard": greeting_card_url,
        "greetingPhoto": greeting_photo_url,
    }


def extract_greeting_card_from_greeting_tree(tree: html.HtmlElement) -> str:
    nodes = tree.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " card_34 ")]'
        '//*[contains(concat(" ", normalize-space(@class), " "), " greeting_thumb ")]'
        '//*[@style]/@style'
    )
    for style in nodes:
        for url in extract_background_urls(style):
            if "hinatazaka46.com/images/14/" in url:
                return url
    return ""


def build_profile_history_entry(
    session: requests.Session,
    image_url: str,
    label: str,
    updated_at: str,
    source_url: str,
    *,
    download_images: bool,
    force_images: bool,
) -> dict:
    return {
        "label": label,
        "updatedAt": updated_at,
        "sourceUrl": source_url,
        "image": archive_member_image_or_empty(
            session,
            image_url,
            PROFILE_ARCHIVE_DIR,
            label,
            download_images=download_images,
            force_images=force_images,
        ),
    }


def build_greeting_history_entry(
    session: requests.Session,
    month: str,
    updated_at: str,
    source_url: str,
    card_url: str,
    photo_url: str,
    *,
    download_images: bool,
    force_images: bool,
) -> dict:
    return {
        "month": month,
        "updatedAt": updated_at,
        "sourceUrl": source_url,
        "greetingCard": archive_member_image_or_empty(
            session,
            card_url,
            GREETING_CARD_ARCHIVE_DIR,
            month,
            download_images=download_images,
            force_images=force_images,
        ),
        "greetingPhoto": archive_member_image_or_empty(
            session,
            photo_url,
            GREETING_PHOTO_ARCHIVE_DIR,
            month,
            download_images=download_images,
            force_images=force_images,
        ),
    }


def should_replace_greeting_month(existing: dict | None, updated_at: str) -> bool:
    if not existing:
        return True
    return str(updated_at) > str(existing.get("updatedAt") or "")


def backfill_member_history(
    session: requests.Session,
    history: dict,
    *,
    download_images: bool,
    force_images: bool,
) -> dict:
    profile_by_image = {
        item.get("image", {}).get("originalSrc"): item
        for item in history.get("profileHistory", [])
        if isinstance(item, dict) and item.get("image", {}).get("originalSrc")
    }
    greeting_by_month = {
        item.get("month"): item
        for item in history.get("greetingHistory", [])
        if isinstance(item, dict) and item.get("month")
    }

    artist_snapshots = fetch_cdx_snapshots(
        session,
        "www.hinatazaka46.com/s/official/artist/34*",
    )
    log(f"wayback artist snapshots: {len(artist_snapshots)}")
    for snapshot in artist_snapshots:
        timestamp = str(snapshot.get("timestamp", ""))
        source_url = archived_snapshot_url(snapshot)
        try:
            tree = html.fromstring(request_text(session, source_url))
        except Exception as exc:
            log(f"warning: failed artist snapshot {timestamp}: {exc}")
            continue

        images = extract_member_images_from_artist_tree(tree)
        label = timestamp_to_jst_month(timestamp)
        updated_at = timestamp_to_iso(timestamp)
        profile_url = images.get("profile", "")
        if profile_url and profile_url not in profile_by_image:
            entry = build_profile_history_entry(
                session,
                profile_url,
                label,
                updated_at,
                source_url,
                download_images=download_images,
                force_images=force_images,
            )
            if entry.get("image", {}).get("src"):
                profile_by_image[profile_url] = entry

        card_url = images.get("greetingCard", "")
        photo_url = images.get("greetingPhoto", "") or infer_greeting_photo_url(card_url)
        if card_url and should_replace_greeting_month(greeting_by_month.get(label), updated_at):
            greeting_by_month[label] = build_greeting_history_entry(
                session,
                label,
                updated_at,
                source_url,
                card_url,
                photo_url,
                download_images=download_images,
                force_images=force_images,
            )
        time.sleep(REQUEST_DELAY_SECONDS)

    greeting_snapshots = fetch_cdx_snapshots(
        session,
        "www.hinatazaka46.com/s/official/page/greeting*",
    )
    log(f"wayback greeting snapshots: {len(greeting_snapshots)}")
    for snapshot in greeting_snapshots:
        timestamp = str(snapshot.get("timestamp", ""))
        month = timestamp_to_jst_month(timestamp)
        updated_at = timestamp_to_iso(timestamp)
        if not should_replace_greeting_month(greeting_by_month.get(month), updated_at):
            continue

        source_url = archived_snapshot_url(snapshot)
        try:
            tree = html.fromstring(request_text(session, source_url))
        except Exception as exc:
            log(f"warning: failed greeting snapshot {timestamp}: {exc}")
            continue

        card_url = extract_greeting_card_from_greeting_tree(tree)
        if not card_url:
            continue
        greeting_by_month[month] = build_greeting_history_entry(
            session,
            month,
            updated_at,
            source_url,
            card_url,
            infer_greeting_photo_url(card_url),
            download_images=download_images,
            force_images=force_images,
        )
        time.sleep(REQUEST_DELAY_SECONDS)

    if download_images:
        for item in profile_by_image.values():
            image = item.get("image", {}) if isinstance(item, dict) else {}
            original = image.get("originalSrc", "")
            if original:
                item["image"] = archive_member_image_or_empty(
                    session,
                    original,
                    PROFILE_ARCHIVE_DIR,
                    str(item.get("label") or timestamp_to_jst_month(str(item.get("updatedAt") or ""))),
                    download_images=download_images,
                    force_images=force_images,
                )

        for item in greeting_by_month.values():
            month = str(item.get("month") or "")
            card = item.get("greetingCard", {}) if isinstance(item, dict) else {}
            photo = item.get("greetingPhoto", {}) if isinstance(item, dict) else {}
            card_original = card.get("originalSrc", "")
            photo_original = photo.get("originalSrc", "") or infer_greeting_photo_url(card_original)
            if card_original:
                item["greetingCard"] = archive_member_image_or_empty(
                    session,
                    card_original,
                    GREETING_CARD_ARCHIVE_DIR,
                    month,
                    download_images=download_images,
                    force_images=force_images,
                )
            if photo_original:
                item["greetingPhoto"] = archive_member_image_or_empty(
                    session,
                    photo_original,
                    GREETING_PHOTO_ARCHIVE_DIR,
                    month,
                    download_images=download_images,
                    force_images=force_images,
                )

    history["profileHistory"] = sorted(
        profile_by_image.values(),
        key=lambda item: str(item.get("updatedAt") or item.get("label") or ""),
        reverse=True,
    )
    history["greetingHistory"] = sorted(
        greeting_by_month.values(),
        key=lambda item: str(item.get("month") or ""),
        reverse=True,
    )
    history["updatedAt"] = utc_now_iso()
    return history


def update_member_history(
    session: requests.Session,
    member: dict,
    *,
    download_images: bool,
    force_images: bool,
) -> dict:
    history = load_member_history()
    now = utc_now_iso()
    month = current_jst_month()
    images = member.get("images") if isinstance(member.get("images"), dict) else {}

    profile = images.get("profile") if isinstance(images.get("profile"), dict) else {}
    profile_original = str(profile.get("originalSrc") or "").strip()
    profile_history = [
        item for item in history.get("profileHistory", []) if isinstance(item, dict)
    ]
    if profile_original and not any(
        item.get("image", {}).get("originalSrc") == profile_original for item in profile_history
    ):
        profile_history.insert(
            0,
            {
                "label": month,
                "updatedAt": now,
                "sourceUrl": member.get("sourceUrl", ""),
                "image": archive_member_image(
                    session,
                    profile_original,
                    PROFILE_ARCHIVE_DIR,
                    month,
                    download_images=download_images,
                    force_images=force_images,
                ),
            },
        )

    greeting_history = [
        item for item in history.get("greetingHistory", []) if isinstance(item, dict)
    ]
    greeting_by_month = {item.get("month"): item for item in greeting_history}
    current_greeting = greeting_by_month.get(month, {"month": month})

    card = images.get("greetingCard") if isinstance(images.get("greetingCard"), dict) else {}
    photo = images.get("greetingPhoto") if isinstance(images.get("greetingPhoto"), dict) else {}
    card_original = str(card.get("originalSrc") or "").strip()
    photo_original = str(photo.get("originalSrc") or "").strip()

    changed = False
    if card_original and current_greeting.get("greetingCard", {}).get("originalSrc") != card_original:
        current_greeting["greetingCard"] = archive_member_image(
            session,
            card_original,
            GREETING_CARD_ARCHIVE_DIR,
            month,
            download_images=download_images,
            force_images=force_images,
        )
        changed = True

    if photo_original and current_greeting.get("greetingPhoto", {}).get("originalSrc") != photo_original:
        current_greeting["greetingPhoto"] = archive_member_image(
            session,
            photo_original,
            GREETING_PHOTO_ARCHIVE_DIR,
            month,
            download_images=download_images,
            force_images=force_images,
        )
        changed = True

    if changed or month not in greeting_by_month:
        current_greeting["updatedAt"] = now
        current_greeting["sourceUrl"] = member.get("sourceUrl", "")
        greeting_by_month[month] = current_greeting

    history["profileHistory"] = sorted(
        profile_history,
        key=lambda item: str(item.get("updatedAt") or item.get("label") or ""),
        reverse=True,
    )
    history["greetingHistory"] = sorted(
        greeting_by_month.values(),
        key=lambda item: str(item.get("month") or ""),
        reverse=True,
    )
    history["updatedAt"] = now
    return history


def update_archive(args: argparse.Namespace) -> None:
    ensure_dirs()
    session = requests.Session()
    session.headers.update(HEADERS)

    existing_posts = load_existing_posts()
    links = collect_post_links(session, max_pages=args.max_pages)
    if args.limit is not None:
        links = links[: args.limit]

    log(f"found {len(links)} official posts")
    posts_by_id = dict(existing_posts)
    refreshed = 0

    for index, link in enumerate(links, start=1):
        if link.post_id in existing_posts and not args.refresh_existing:
            continue

        log(f"[{index}/{len(links)}] fetching {link.post_id}")
        posts_by_id[link.post_id] = parse_post(
            session,
            link,
            download_images=not args.no_images,
            force_images=args.force_images,
        )
        refreshed += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    posts = sort_posts(posts_by_id.values())
    write_json(POSTS_PATH, posts)

    member = None
    try:
        member = parse_member(
            session,
            download_images=not args.no_images,
            force_images=args.force_images,
        )
        write_json(MEMBER_PATH, member)
        member_history = update_member_history(
            session,
            member,
            download_images=not args.no_images,
            force_images=args.force_images,
        )
        if args.backfill_member_history:
            member_history = backfill_member_history(
                session,
                member_history,
                download_images=not args.no_images,
                force_images=args.force_images,
            )
        write_json(MEMBER_HISTORY_PATH, member_history)
    except Exception as exc:
        log(f"warning: failed to update member profile/history: {exc}")

    now = utc_now_iso()
    write_json(
        META_PATH,
        {
            "memberId": int(MEMBER_ID),
            "memberName": member.get("name") if member else MEMBER_NAME,
            "postCount": len(posts),
            "latestPostId": posts[0]["id"] if posts else None,
            "latestPostDate": posts[0]["date"] if posts else None,
            "updatedAt": now,
            "source": f"{BASE_URL}/s/official/diary/member/list?ima=0000&ct={MEMBER_ID}",
        },
    )
    log(f"wrote {len(posts)} posts ({refreshed} refreshed)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=None, help="Only scan the first N list pages.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N discovered posts.")
    parser.add_argument("--refresh-existing", action="store_true", help="Re-parse posts already present in data.")
    parser.add_argument("--no-images", action="store_true", help="Store official CDN image URLs without downloading.")
    parser.add_argument("--force-images", action="store_true", help="Re-download images even when files already exist.")
    parser.add_argument(
        "--backfill-member-history",
        action="store_true",
        help="Backfill profile and greeting archives from Wayback Machine snapshots.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    update_archive(parse_args())
