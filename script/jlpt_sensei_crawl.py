import requests
from pathlib import Path

BASE_URL = "https://jlptvietnam.com/danh-sach-ngu-phap-n{level}"
PAGE_COUNTS = {
    1: 2,
    2: 6,
    3: 5,
    4: 3,
    5: 2,
}

OUTPUT_DIR = Path("temp/jlpt_sensei")
OUTPUT_DIR.mkdir(exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0"
}

for level, page_count in PAGE_COUNTS.items():
    level_dir = OUTPUT_DIR / f"N{level}"
    level_dir.mkdir(exist_ok=True)

    for page in range(1, page_count + 1):
        if page == 1:
            url = f"{BASE_URL.format(level=level)}/"
        else:
            url = f"{BASE_URL.format(level=level)}/page/{page}/"

        print(f"Downloading: {url}")

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        output_file = level_dir / f"page_{page}.html"
        output_file.write_text(response.text, encoding="utf-8")

        print(f"  -> {output_file}")

print("Done.")