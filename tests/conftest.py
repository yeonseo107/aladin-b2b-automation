"""테스트 공용 픽스처/헬퍼."""
from aladin_automation.aladin_client import Book


def make_book(
    title: str,
    *,
    author: str = "저자",
    publisher: str = "출판사",
    isbn13: str = "9788900000000",
    price_standard: int = 10000,
    price_sales: int = 9000,
    stock_status: str = "",
) -> Book:
    """테스트용 Book 생성 (네트워크 없이 매칭/견적 로직 검증)."""
    return Book(
        title=title,
        author=author,
        publisher=publisher,
        pub_date="2024-01-01",
        isbn13=isbn13,
        price_standard=price_standard,
        price_sales=price_sales,
        stock_status=stock_status,
        category_name="국내도서",
    )
