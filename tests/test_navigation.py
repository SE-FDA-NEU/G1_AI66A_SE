"""Every P0 story starts from a link, so nobody has to type a URL (Milestone 3, #85)."""

from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.hrefs.add(href)


def links(client: TestClient, path: str) -> set[str]:
    parser = Links()
    parser.feed(client.get(path).text)
    return parser.hrefs


def test_the_catalog_links_to_every_screen_where_a_p0_story_starts(client: TestClient) -> None:
    # US01 is the catalog itself and US02 starts from its product cards; the others start here.
    assert {"/products", "/cart", "/seller/products/new", "/seller/orders"} <= links(
        client, "/products"
    )


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ("/seller/products/new", {"/products", "/seller/orders"}),
        ("/seller/orders", {"/products", "/seller/products/new"}),
        ("/cart", {"/products"}),
        ("/checkout", {"/products", "/cart"}),
    ],
)
def test_each_screen_links_back_to_the_others(
    client: TestClient, page: str, expected: set[str]
) -> None:
    assert expected <= links(client, page)


def test_the_root_url_opens_the_catalog_in_a_browser(client: TestClient) -> None:
    response = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/products"
