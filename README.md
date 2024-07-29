# scrapy-nodriver: Nodriver integration for Scrapy
[![version](https://img.shields.io/pypi/v/scrapy-nodriver.svg)](https://pypi.python.org/pypi/scrapy-nodriver)
[![pyversions](https://img.shields.io/pypi/pyversions/scrapy-nodriver.svg)](https://pypi.python.org/pypi/scrapy-nodriver)


A [Scrapy](https://github.com/scrapy/scrapy) Download Handler which performs requests using
[Nodriver for Python](https://github.com/ultrafunkamsterdam/nodriver).
It can be used to handle pages that require JavaScript (among other things),
while adhering to the regular Scrapy workflow (i.e. without interfering
with request scheduling, item processing, etc).


## Requirements

After the release of [version 2.0](https://docs.scrapy.org/en/latest/news.html#scrapy-2-0-0-2020-03-03),
which includes [coroutine syntax support](https://docs.scrapy.org/en/2.0/topics/coroutines.html)
and [asyncio support](https://docs.scrapy.org/en/2.0/topics/asyncio.html), Scrapy allows
to integrate `asyncio`-based projects such as `Nodriver`.


### Minimum required versions

* Python >= 3.8
* Scrapy >= 2.0 (!= 2.4.0)


## Installation

`scrapy-nodriver` is available on PyPI and can be installed with `pip`:

```
pip install scrapy-nodriver
```

`nodriver` is defined as a dependency so it gets installed automatically,


## Changelog

See the [changelog](docs/changelog.md) document.


## Activation

### Download handler

Replace the default `http` and/or `https` Download Handlers through
[`DOWNLOAD_HANDLERS`](https://docs.scrapy.org/en/latest/topics/settings.html):

```python
# settings.py
DOWNLOAD_HANDLERS = {
    "http": "scrapy_nodriver.handler.ScrapyNodriverDownloadHandler",
    "https": "scrapy_nodriver.handler.ScrapyNodriverDownloadHandler",
}
```

Note that the `ScrapyNodriverDownloadHandler` class inherits from the default
`http/https` handler. Unless explicitly marked (see [Basic usage](#basic-usage)),
requests will be processed by the regular Scrapy download handler.


### Twisted reactor

[Install the `asyncio`-based Twisted reactor](https://docs.scrapy.org/en/latest/topics/asyncio.html#installing-the-asyncio-reactor):

```python
# settings.py
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
```

This is the default in new projects since [Scrapy 2.7](https://github.com/scrapy/scrapy/releases/tag/2.7.0).


## Basic usage

Set the [`nodriver`](#nodriver) [Request.meta](https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta)
key to download a request using Nodriver:

```python
import scrapy

class AwesomeSpider(scrapy.Spider):
    name = "awesome"

    def start_requests(self):
        # GET request
        yield scrapy.Request("https://httpbin.org/get", meta={"nodriver": True})
        # POST request
        yield scrapy.FormRequest(
            url="https://httpbin.org/post",
            formdata={"foo": "bar"},
            meta={"nodriver": True},
        )

    def parse(self, response, **kwargs):
        # 'response' contains the page as seen by the browser
        return {"url": response.url}
```


settings.py
```python
NODRIVER_HEADLESS = True  
NODRIVER_MAX_CONCURRENT_PAGES = 8  # defaults to the value of Scrapy's CONCURRENT_REQUESTS setting
# block images
NODRIVER_BLOCKED_URLS = [
    */*.jpg",
    */*.png",
    */*.gif",
    */*.webp",
    */*.svg",
    */*.ico"
]
```


### General note about settings
For settings that accept object paths as strings, passing callable objects is
only supported when using Scrapy>=2.4. With prior versions, only strings are
supported.



## Supported [`Request.meta`](https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta) keys

### `nodriver`
Type `bool`, default `False`

If set to a value that evaluates to `True` the request will be processed by Nodriver.

```python
return scrapy.Request("https://example.org", meta={"nodriver": True})
```

### `nodriver_include_page`
Type `bool`, default `False`

If `True`, the [Nodriver page]
that was used to download the request will be available in the callback at
`response.meta['nodriver_page']`. If `False` (or unset) the page will be
closed immediately after processing the request.

**Important!**

This meta key is entirely optional, it's NOT necessary for the page to load or for any
asynchronous operation to be performed (specifically, it's NOT necessary for `PageMethod`
objects to be applied). Use it only if you need access to the Page object in the callback
that handles the response.

For more information and important notes see
[Receiving Page objects in callbacks](#receiving-page-objects-in-callbacks).

```python
return scrapy.Request(
    url="https://example.org",
    meta={"nodriver": True, "nodriver_include_page": True},
)
```

### `nodriver_page_methods`
Type `Iterable[PageMethod]`, default `()`

An iterable of [`scrapy_nodriver.page.PageMethod`](#pagemethod-class)
objects to indicate actions to be performed on the page before returning the
final response. See [Executing actions on pages](#executing-actions-on-pages).

### `nodriver_page`
Type `Optional[nodriver.Tab]`, default `None`

A [Nodriver page]() to be used to
download the request. If unspecified, a new page is created for each request.
This key could be used in conjunction with `nodriver_include_page` to make a chain of
requests using the same page. For instance:

```python
from nodriver import Tab

def start_requests(self):
    yield scrapy.Request(
        url="https://httpbin.org/get",
        meta={"nodriver": True, "nodriver_include_page": True},
    )

def parse(self, response, **kwargs):
    page: Tab = response.meta["nodriver_page"]
    yield scrapy.Request(
        url="https://httpbin.org/headers",
        callback=self.parse_headers,
        meta={"nodriver": True, "nodriver_page": page},
    )
```

```python
from nodriver import Tab
import scrapy

class AwesomeSpiderWithPage(scrapy.Spider):
    name = "page_spider"

    def start_requests(self):
        yield scrapy.Request(
            url="https://example.org",
            callback=self.parse_first,
            meta={"nodriver": True, "nodriver_include_page": True},
            errback=self.errback_close_page,
        )

    def parse_first(self, response):
        page: Page = response.meta["nodriver_page"]
        return scrapy.Request(
            url="https://example.com",
            callback=self.parse_second,
            meta={"nodriver": True, "nodriver_include_page": True, "nodriver_page": page},
            errback=self.errback_close_page,
        )

    async def parse_second(self, response):
        page: Page = response.meta["nodriver_page"]
        title = await page.title()  # "Example Domain"
        await page.close()
        return {"title": title}

    async def errback_close_page(self, failure):
        page: Page = failure.request.meta["nodriver_page"]
        await page.close()
```

**Notes:**

* When passing `nodriver_include_page=True`, make sure pages are always closed
  when they are no longer used. It's recommended to set a Request errback to make
  sure pages are closed even if a request fails (if `nodriver_include_page=False`
  pages are automatically closed upon encountering an exception).
  This is important, as open pages count towards the limit set by
  `NODRIVER_MAX_CONCURRENT_PAGES` and crawls could freeze if the limit is reached
  and pages remain open indefinitely.
* Defining callbacks as `async def` is only necessary if you need to `await` things,
  it's NOT necessary if you just need to pass over the Page object from one callback
  to another (see the example above).
* Any network operations resulting from awaiting a coroutine on a Page object
  (`get`, etc) will be executed directly by Nodriver, bypassing the
  Scrapy request workflow (Scheduler, Middlewares, etc).



## Executing actions on pages

A sorted iterable (e.g. `list`, `tuple`, `dict`) of `PageMethod` objects
could be passed in the `nodriver_page_methods`
[Request.meta](https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta)
key to request methods to be invoked on the `Page` object before returning the final
`Response` to the callback.

This is useful when you need to perform certain actions on a page (like scrolling
down or clicking links) and you want to handle only the final result in your callback.

### `PageMethod` class

#### `scrapy_nodriver.page.PageMethod(method: str, *args, **kwargs)`:

Represents a method to be called (and awaited if necessary) on a
`nodriver.Tab` object (e.g. "select", "save_screenshot", "evaluate", etc).
`method` is the name of the method, `*args` and `**kwargs`
are passed when calling such method. The return value
will be stored in the `PageMethod.result` attribute.

For instance:
```python
def start_requests(self):
    yield Request(
        url="https://example.org",
        meta={
            "nodriver": True,
            "nodriver_page_methods": [
                PageMethod("save_screenshot", filename="example.jpeg", full_page=True),
            ],
        },
    )

def parse(self, response, **kwargs):
    screenshot = response.meta["nodriver_page_methods"][0]
    # screenshot.result contains the image file path
```

produces the same effect as:
```python
def start_requests(self):
    yield Request(
        url="https://example.org",
        meta={"nodriver": True, "nodriver_include_page": True},
    )

async def parse(self, response, **kwargs):
    page = response.meta["nodriver_page"]
    filepath = await page.save_screenshot(filename="example.jpeg", full_page=True)
    await page.close()
```


### Supported methods

Refer to the [upstream docs for the `Tab` class](https://github.com/ultrafunkamsterdam/nodriver)
to see available methods.


**Scroll down on an infinite scroll page, take a screenshot of the full page**

```python
class ScrollSpider(scrapy.Spider):
    name = "scroll"

    def start_requests(self):
        yield scrapy.Request(
            url="http://quotes.toscrape.com/scroll",
            meta=dict(
                nodriver=True,
                nodriver_include_page=True,
                nodriver_page_methods=[
                    PageMethod("wait_for", "div.quote"),
                    PageMethod("evaluate", "window.scrollBy(0, document.body.scrollHeight)"),
                    PageMethod("wait_for", "div.quote:nth-child(11)"),  # 10 per page
                ],
            ),
        )

    async def parse(self, response, **kwargs):
        page = response.meta["nodriver_page"]
        await page.save_screenshot(filename="quotes.jpeg", full_page=True)
        await page.close()
        return {"quote_count": len(response.css("div.quote"))}  # quotes from several pages
```



## Known issues

### No proxy support
Specifying a proxy via the `proxy` Request meta key is not supported.

## Reporting issues

Before opening an issue please make sure the unexpected behavior can only be
observed by using this package and not with standalone Nodriver. To do this,
translate your spider code to a reasonably close Nodriver script: if the
issue also occurs this way, you should instead report it
[upstream](https://github.com/ultrafunkamsterdam/nodriver).
For instance:

```python
import scrapy

class ExampleSpider(scrapy.Spider):
    name = "example"

    def start_requests(self):
        yield scrapy.Request(
            url="https://example.org",
            meta=dict(
                nodriver=True,
                nodriver_page_methods=[
                    PageMethod("save_screenshot", filename="example.jpeg", full_page=True),
                ],
            ),
        )
```

translates roughly to:

```python
import asyncio
import nodriver as uc

async def main():
    browser = await uc.start()
    page = await browser.get("https://example.org")
    await page.save_screenshot(filename="example.jpeg", full_page=True)
    await page.close()

if __name__ == '__main__':
    uc.loop().run_until_complete(main())
```