import asyncio
import logging
import time
from functools import partial
from typing import Type, TypeVar, List
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from dataclasses import dataclass
from scrapy.settings import Settings
from scrapy.crawler import Crawler
from scrapy.utils.reactor import verify_installed_reactor
from scrapy import signals, Spider
from twisted.internet.defer import Deferred, inlineCallbacks
from scrapy.utils.defer import deferred_from_coro
import nodriver as uc
from scrapy.http import Request, Response
from nodriver import Tab
from scrapy.responsetypes import responsetypes

from scrapy_nodriver._utils import (
    _encode_body,
    _get_header_value,
    _maybe_await,
)


logging.getLogger("websockets.client").setLevel(logging.ERROR)
logging.getLogger("uc").setLevel(logging.ERROR)
logging.getLogger("nodriver").setLevel(logging.ERROR)
logger = logging.getLogger("scrapy-nodriver")

__all__ = ['ScrapyNodriverDownloadHandler']

NodriverHandler = TypeVar("NodriverHandler", bound="ScrapyNodriverDownloadHandler")



@dataclass
class Config:
    max_concurrent_pages: int
    headless: bool
    blocked_urls: List
    target_closed_max_retries: int = 3


    @classmethod
    def from_settings(cls, settings: Settings) -> "Config":
        cfg = cls(
            max_concurrent_pages=settings.getint("CONCURRENT_REQUESTS") if not settings.getint("NODRIVER_MAX_CONCURRENT_PAGES") else settings.getint("NODRIVER_MAX_CONCURRENT_PAGES"),
            headless=settings.getbool("NODRIVER_HEADLESS", default=True),
            blocked_urls=settings.getlist("NODRIVER_BLOCKED_URLS"),
        )
        return cfg



class ScrapyNodriverDownloadHandler(HTTPDownloadHandler):
    
    def __init__(self, crawler: Crawler):
        super().__init__(settings=crawler.settings, crawler=crawler)
        verify_installed_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
        crawler.signals.connect(self._engine_started, signals.engine_started)
        self.stats = crawler.stats
        self.config = Config.from_settings(crawler.settings)
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_pages)
        self.pages = 0

    
    @classmethod
    def from_crawler(cls: Type[NodriverHandler], crawler: Crawler) -> NodriverHandler:
        return cls(crawler)
    

    def _engine_started(self) -> Deferred:
        """Launch the browser. Use the engine_started signal as it supports returning deferreds."""
        return deferred_from_coro(self._launch())


    def _get_total_page_count(self):
        return self.pages


    def _set_max_concurrent_page_count(self):
        count = self._get_total_page_count()
        current_max_count = self.stats.get_value("nodriver/page_count/max_concurrent")
        if current_max_count is None or count > current_max_count:
            self.stats.set_value("nodriver/page_count/max_concurrent", count)


    async def _launch(self) -> None:
        logger.info("Starting download handler")


    async def _create_page(self, request: Request, spider: Spider) -> Tab:
        await self.semaphore.acquire()
        browser = await uc.start(headless=self.config.headless)
        page = await browser.get()
        self.pages += 1
        self.stats.inc_value("nodriver/page_count")
        logger.debug(
            "New page created, page count is %i",
            self._get_total_page_count(),
            extra={
                "spider": spider,
                "total_page_count": self._get_total_page_count(),
                "scrapy_request_url": request.url,
                "scrapy_request_method": request.method,
            },
        )
        self._set_max_concurrent_page_count()

        page.add_handler(uc.cdp.network.RequestWillBeSent, self._increment_request_stats)
        page.add_handler(uc.cdp.network.ResponseReceived, self._increment_response_stats)
        page.add_handler(uc.cdp.network.RequestWillBeSent, partial(self._log_request, spider=spider))
        page.add_handler(uc.cdp.network.ResponseReceived, partial(self._log_response, spider=spider))
        page.add_handler(uc.cdp.network.LoadingFailed, partial(self._log_blocked_request))
        
        if self.config.blocked_urls:
            await page.send(uc.cdp.network.enable())
            await page.send(uc.cdp.network.set_blocked_ur_ls(self.config.blocked_urls))

        page.on("close", self._close_page_callback)
        return page


    @inlineCallbacks
    def close(self) -> Deferred:
        logger.info("Closing download handler")
        yield super().close()
        yield deferred_from_coro(self._close())

    
    async def _close(self) -> None:
        logger.info("Closing browser")

    
    def download_request(self, request: Request, spider: Spider) -> Deferred:
        if request.meta.get("nodriver"):
            return deferred_from_coro(self._download_request(request, spider))
        return super().download_request(request, spider)
    

    async def _download_request(self, request: Request, spider: Spider) -> Response:
        counter = 0
        while True:
            try:
                return await self._download_request_with_retry(request=request, spider=spider)
            except Exception as ex:
                counter += 1
                if counter > self.config.target_closed_max_retries:
                    raise ex
                logger.debug(
                    "Target closed, retrying to create page for %s",
                    request,
                    extra={
                        "spider": spider,
                        "scrapy_request_url": request.url,
                        "scrapy_request_method": request.method,
                        "exception": ex,
                    },
                )

    
    async def _download_request_with_retry(self, request: Request, spider: Spider) -> Response:
        page: Tab = request.meta.get("nodriver_page")
        if not isinstance(page, Tab) or page.closed:
            page = await self._create_page(request=request, spider=spider)
        
        try:
            return await self._download_request_with_page(request, page, spider)
        except Exception as ex:
            if not request.meta.get("nodriver_include_page") and not page.closed:
                logger.warning(
                    "Closing page due to failed request: %s exc_type=%s exc_msg=%s",
                    request,
                    type(ex),
                    str(ex),
                    extra={
                        "spider": spider,
                        "scrapy_request_url": request.url,
                        "scrapy_request_method": request.method,
                        "exception": ex,
                    },
                    exc_info=True,
                )
                await page.close()
                self.stats.inc_value("nodriver/page_count/closed")
            raise

    
    async def _download_request_with_page(self, request: Request, page: Tab, spider: Spider) -> Response:
        if request.meta.get("nodriver_include_page"):
            request.meta["nodriver_page"] = page
        
        start_time = time.time()
        headers = {}
        def capture_headers(event: uc.cdp.network.RequestWillBeSent):
            nonlocal headers
            if event.request.url.strip("/") == request.url.strip("/"):
                headers = dict(event.request.headers)
        page.add_handler(uc.cdp.network.RequestWillBeSent, capture_headers)

        try:
            await page.get(request.url)
        except Exception as ex:
            logger.debug(
                "Navigating to %s failed",
                request.url,
                extra={
                    "spider": spider,
                    "scrapy_request_url": request.url,
                    "scrapy_request_method": request.method,
                },
            )
        await self._apply_page_methods(page, request, spider)
        body_str = await page.get_content()
        request.meta["download_latency"] = time.time() - start_time

        if not request.meta.get("nodriver_include_page"):
            await page.close()
            self.stats.inc_value("nodriver/page_count/closed")

        body, encoding = _encode_body(headers=headers, text=body_str)
        respcls = responsetypes.from_args(headers=headers, url=request.url, body=body)
        return respcls(
            url=request.url,
            status=200,
            headers=headers,
            body=body,
            request=request,
            flags=["nodriver"],
            encoding=encoding,
            ip_address=None,
        )
    

    async def _apply_page_methods(self, page: Tab, request: Request, spider: Spider) -> None:
        page_methods = request.meta.get("nodriver_page_methods") or ()
        for pm in page_methods:
            try:
                method = getattr(page, pm.method)
            except AttributeError as ex:
                logger.warning(
                    "Ignoring %r: could not find method",
                    pm,
                    extra={
                        "spider": spider,
                        "scrapy_request_url": request.url,
                        "scrapy_request_method": request.method,
                        "exception": ex,
                    },
                    exc_info=True,
                )
            else:
                pm.result = await _maybe_await(method(*pm.args, **pm.kwargs))
                await page.wait()


    def _increment_request_stats(self, event: uc.cdp.network.RequestWillBeSent) -> None:
        stats_prefix = "nodriver/request_count"
        self.stats.inc_value(stats_prefix)
        self.stats.inc_value(f"{stats_prefix}/resource_type/{event.type_.value}")


    def _increment_response_stats(self, event: uc.cdp.network.ResponseReceived) -> None:
        stats_prefix = "nodriver/response_count"
        self.stats.inc_value(stats_prefix)
        self.stats.inc_value(f"{stats_prefix}/resource_type/{event.type_.value}")


    @staticmethod
    def _log_request(event: uc.cdp.network.RequestWillBeSent, spider: Spider) -> None:
        log_args = [event.request.method.upper(), event.request.url, event.type_.value]
        referrer = _get_header_value(event.request, "referer")
        if referrer:
            log_args.append(referrer)
            log_msg = "Request: <%s %s> (resource type: %s, referrer: %s)"
        else:
            log_msg = "Request: <%s %s> (resource type: %s)"
        logger.debug(
            log_msg,
            *log_args,
            extra={
                "spider": spider,
                "nodriver_request_url": event.request.url,
                "nodriver_request_method": event.request.method.upper(),
                "nodriver_resource_type": event.type_.value,
            },
        )


    @staticmethod
    def _log_response(event: uc.cdp.network.ResponseReceived, spider: Spider) -> None:
        log_args = [event.response.status, event.response.url]
        location = _get_header_value(event.response, "location")
        if location:
            log_args.append(location)
            log_msg = "Response: <%i %s> (location: %s)"
        else:
            log_msg = "Response: <%i %s>"
        logger.debug(
            log_msg,
            *log_args,
            extra={
                "spider": spider,
                "nodriver_response_url": event.response.url,
                "nodriver_response_status": event.response.status,
            },
        )


    def _log_blocked_request(self, event: uc.cdp.network.LoadingFailed) -> None:
        if event.blocked_reason.value == "inspector":
            self.stats.inc_value("nodriver/request_count/aborted")


    def _close_page_callback(self) -> None:
        self.pages -=1
        self.semaphore.release()

