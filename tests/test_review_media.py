"""Task #131's additive media contract; eligibility rules remain in #130."""

import json

import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine, select

from src.database import engine, migrate_db
from src.models.review import Review
from tests.test_us15_reviews_notifications import (
    BUYER_EMAIL,
    PRODUCT_CODE,
    SELLER_EMAIL,
    _auth,
    _token,
)
from tests.test_us15_reviews_notifications import (
    us15_data as us15_data,
)


def test_review_media_urls_persist_and_return_with_seller_timestamp(client, us15_data):
    urls = ["https://example.com/photo.jpg", "https://example.com/clip.mp4"]
    response = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(_token(client, BUYER_EMAIL)),
        json={"order_item_id": us15_data["completed_item_id"], "rating": 4, "media_urls": urls},
    )
    assert response.status_code == 201
    review = response.json()["data"]
    assert review["media_urls"] == urls
    assert review["media_url"] == urls[0]
    assert review["seller_replied_at"] is None
    with Session(engine) as session:
        saved = session.get(Review, review["id"])
        assert json.loads(saved.images_json) == urls
    listed = client.get(f"/api/v1/products/{PRODUCT_CODE}/reviews").json()["data"]
    assert listed[0]["media_urls"] == urls
    assert listed[0]["created_at"].endswith("Z")
    replied = client.patch(
        f"/api/v1/seller/reviews/{review['id']}/reply",
        headers=_auth(_token(client, SELLER_EMAIL)), json={"reply": "Thanks for sharing."},
    )
    assert replied.status_code == 200
    assert replied.json()["data"]["media_urls"] == urls
    assert replied.json()["data"]["seller_replied_at"].endswith("Z")


def test_legacy_media_url_remains_supported(client, us15_data):
    url = "https://example.com/legacy.png"
    response = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(_token(client, BUYER_EMAIL)),
        json={"order_item_id": us15_data["completed_item_id"], "rating": 5, "media_url": url},
    )
    assert response.status_code == 201
    assert response.json()["data"]["media_url"] == url
    assert response.json()["data"]["media_urls"] == [url]


@pytest.mark.parametrize("duplicate,expected_status", [(True, 201), (False, 422)])
def test_combined_legacy_and_collection_limit(client, us15_data, duplicate, expected_status):
    urls = [f"https://example.com/{i}.jpg" for i in range(5)]
    response = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(_token(client, BUYER_EMAIL)),
        json={"order_item_id": us15_data["completed_item_id"], "rating": 5,
              "media_urls": urls,
              "media_url": urls[0] if duplicate else "https://example.com/sixth.jpg"},
    )
    assert response.status_code == expected_status
    if duplicate:
        assert response.json()["data"]["media_urls"] == urls
    else:
        with Session(engine) as session:
            assert session.exec(select(Review)).all() == []


@pytest.mark.parametrize("urls", [
    ["javascript:alert(1)"], ["file:///photo.png"], ["not-a-url"],
    [f"https://example.com/{i}.jpg" for i in range(6)],
    ["https://example.com/" + "x" * 2048],
])
def test_invalid_review_media_is_rejected_without_saving(client, us15_data, urls):
    response = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(_token(client, BUYER_EMAIL)),
        json={"order_item_id": us15_data["completed_item_id"], "rating": 5, "media_urls": urls},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ERR_VALIDATION"
    with Session(engine) as session:
        assert session.exec(select(Review)).all() == []


@pytest.mark.parametrize("count", [0, 1, 5])
def test_review_media_accepts_empty_single_and_maximum_list(client, us15_data, count):
    urls = [f"https://example.com/{i}.jpg" for i in range(count)]
    response = client.post(
        f"/api/v1/products/{PRODUCT_CODE}/reviews",
        headers=_auth(_token(client, BUYER_EMAIL)),
        json={"order_item_id": us15_data["completed_item_id"], "rating": 5, "media_urls": urls},
    )
    assert response.status_code == 201
    assert response.json()["data"]["media_urls"] == urls


def test_review_media_migration_preserves_legacy_links_and_is_repeatable(tmp_path):
    media_engine = create_engine(f"sqlite:///{tmp_path / 'legacy_reviews.db'}")
    with media_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE reviews (id INTEGER PRIMARY KEY, media_url TEXT, comment TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO reviews VALUES (1, 'https://example.com/old.jpg', 'Keep me'), "
            "(2, NULL, 'No media')"
        )
        migrate_db(connection)
        rows = connection.execute(text("SELECT comment, images_json FROM reviews ORDER BY id"))
        assert [(row[0], json.loads(row[1])) for row in rows] == [
            ("Keep me", ["https://example.com/old.jpg"]), ("No media", []),
        ]
        connection.execute(text("UPDATE reviews SET images_json = :refs WHERE id = 2"),
                           {"refs": json.dumps(["https://example.com/new.webm"])})
        migrate_db(connection)
        assert json.loads(connection.execute(
            text("SELECT images_json FROM reviews WHERE id = 2")
        ).scalar_one()) == ["https://example.com/new.webm"]
    media_engine.dispose()
