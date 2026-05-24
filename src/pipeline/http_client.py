from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


@dataclass
class FetchedPage:
    url: str
    final_url: str
    title: str
    text: str
    links: list[str]


def _clean_text(html: str) -> tuple[str, str, list[str]]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = " ".join(soup.get_text(" ", strip=True).split())
    links = [anchor.get("href") for anchor in soup.find_all("a") if anchor.get("href")]
    return title, text, links


def fetch_page(url: str, timeout: int = 20) -> FetchedPage:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "ai-web-scraping-pipeline/0.1"})
    response.raise_for_status()
    title, text, raw_links = _clean_text(response.text)
    final_url = response.url
    links = []
    for raw_link in raw_links:
        absolute = urljoin(final_url, raw_link)
        parsed = urlparse(absolute)
        if parsed.scheme in {"http", "https"}:
            normalized = parsed._replace(fragment="").geturl()
            if normalized not in links:
                links.append(normalized)
    return FetchedPage(url=url, final_url=final_url, title=title, text=text, links=links)
