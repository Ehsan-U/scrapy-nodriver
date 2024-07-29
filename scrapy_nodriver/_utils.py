
from scrapy.http.headers import Headers
from typing import Awaitable, Iterator, Optional, Tuple
from scrapy.utils.python import to_unicode
from w3lib.encoding import html_body_declared_encoding, http_content_type_encoding
import nodriver as uc


async def _maybe_await(obj):
    if isinstance(obj, Awaitable):
        return await obj
    return obj


def _possible_encodings(headers: Headers, text: str) -> Iterator[str]:
    if headers.get("content-type"):
        content_type = to_unicode(headers["content-type"])
        yield http_content_type_encoding(content_type)
    yield html_body_declared_encoding(text)


def _encode_body(headers: Headers, text: str) -> Tuple[bytes, str]:
    for encoding in filter(None, _possible_encodings(headers, text)):
        try:
            body = text.encode(encoding)
        except UnicodeEncodeError:
            pass
        else:
            return body, encoding
    return text.encode("utf-8"), "utf-8"  # fallback


def _get_header_value(
    resource: uc.cdp.network.Request | uc.cdp.network.Response,
    header_name: str,
) -> Optional[str]:
    try:
        for header, value in resource.headers.items():
            if header.lower() in header_name:
                return value
    except Exception:
        return None