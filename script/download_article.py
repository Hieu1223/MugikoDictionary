import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


SOURCE_DIR = Path("temp/jlpt_sensei")

URL_PREFIX = (
    "https://jlptvietnam.com/tieng-nhat/"
    "hoc-ngu-phap-jlpt-"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def extract_urls(html: str):
    soup = BeautifulSoup(html, "lxml")

    urls = set()

    for link in soup.find_all("a", href=True):
        url = urljoin(
            "https://jlptvietnam.com/",
            link["href"],
        )

        if url.startswith(URL_PREFIX):
            urls.add(url)

    return sorted(urls)


def download(
    url: str,
    output_file: Path,
    session: requests.Session,
):
    print(f"Downloading: {url}")

    response = session.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    output_file.write_text(
        response.text,
        encoding="utf-8",
    )


def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    total = 0

    for level_dir in sorted(
        SOURCE_DIR.glob("N*")
    ):
        if not level_dir.is_dir():
            continue

        if not re.fullmatch(
            r"N[1-5]",
            level_dir.name,
        ):
            continue

        for source_file in sorted(
            level_dir.glob("page_*.html")
        ):
            print(f"\nProcessing: {source_file}")

            html = source_file.read_text(
                encoding="utf-8"
            )

            urls = extract_urls(html)

            print(
                f"Found {len(urls)} URLs"
            )

            # Keep the same source structure:
            #
            # N1/
            #   page_1.html
            #   page_2.html
            #   articles/
            #       page_1/
            #       page_2/
            #
            article_dir = (
                level_dir
                / "articles"
                / source_file.stem
            )

            article_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            for url in urls:
                slug = (
                    url.rstrip("/")
                    .split("/")[-1]
                )

                output_file = (
                    article_dir
                    / f"{slug}.html"
                )

                if output_file.exists():
                    print(
                        f"Already exists: "
                        f"{output_file}"
                    )
                    continue

                try:
                    download(
                        url,
                        output_file,
                        session,
                    )

                    total += 1

                    print(
                        f"  -> {output_file}"
                    )

                except requests.RequestException as e:
                    print(
                        f"  ERROR: {url}"
                    )
                    print(
                        f"         {e}"
                    )

    print("\nDone.")
    print(
        f"Downloaded: {total} articles"
    )


if __name__ == "__main__":
    main()