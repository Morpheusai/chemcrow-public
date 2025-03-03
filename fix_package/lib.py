from __future__ import annotations
from pathlib import Path
import asyncio
import contextlib
import logging
import os
import re
import sys
from collections.abc import Iterable
from enum import Enum, IntEnum, auto
from functools import partial
from pathlib import Path
from typing import Any

from aiohttp import ClientResponse, ClientResponseError, ClientSession, InvalidURL

from .exceptions import CitationConversionError, DOINotFoundError, NoPDFLinkError
from .headers import get_header
from .log_formatter import CustomFormatter
from .scraper import Scraper
from .utils import (
    ThrottledClientSession,
    crossref_headers,
    encode_id,
    find_doi,
    get_scheme_hostname,
    search_pdf_link,
)

year_extract_pattern = re.compile(r"\b\d{4}\b")


def clean_upbibtex(bibtex: str) -> str:
    # WTF Semantic Scholar?
    mapping = {
        "None": "article",
        "Article": "article",
        "JournalArticle": "article",
        "Review": "article",
        "Book": "book",
        "BookSection": "inbook",
        "ConferencePaper": "inproceedings",
        "Conference": "inproceedings",
        "Dataset": "misc",
        "Dissertation": "phdthesis",
        "Journal": "article",
        "Patent": "patent",
        "Preprint": "article",
        "Report": "techreport",
        "Thesis": "phdthesis",
        "WebPage": "misc",
        "Plain": "article",
    }

    if "@None" in bibtex:
        return bibtex.replace("@None", "@article")
    # new format check
    match = re.findall(r"@\['(.*)'\]", bibtex)
    if len(match) == 0:
        match = re.findall(r"@(.*)\{", bibtex)
        bib_type = match[0]
        current = f"@{match[0]}"
    else:
        bib_type = match[0]
        current = f"@['{bib_type}']"
    for k, v in mapping.items():
        # can have multiple
        if k in bib_type:
            bibtex = bibtex.replace(current, f"@{v}")
            break
    return bibtex


def format_bibtex(bibtex, key, clean: bool = True) -> str:
    # WOWOW This is hard to use
    from pybtex.database import parse_string
    from pybtex.style.formatting import unsrtalpha
    from pybtex.style.template import FieldIsMissing

    style = unsrtalpha.Style()
    try:
        bd = parse_string(clean_upbibtex(bibtex) if clean else bibtex, "bibtex")
    except Exception:
        return "Ref " + key
    try:
        entry = style.format_entry(label="1", entry=bd.entries[key])
        return entry.text.render_as("text")
    except (FieldIsMissing, UnicodeDecodeError):
        try:
            return bd.entries[key].fields["title"]
        except KeyError as exc:
            raise CitationConversionError(
                f"Failed to process{' and clean up' if clean else ''} bibtex {bibtex}"
                " due to missing a 'title' field."
            ) from exc


async def likely_pdf(response: ClientResponse) -> bool:
    try:
        text = await response.text()
        if "Invalid article ID" in text:
            return False
        if "No paper" in text:
            return False
    except UnicodeDecodeError:
        return True
    return True


async def arxiv_to_pdf(arxiv_id, path, session: ClientSession) -> None:
    # download
    async with session.get(
        f"https://arxiv.org/pdf/{arxiv_id}.pdf", allow_redirects=True
    ) as r:
        if not r.ok or not await likely_pdf(r):
            raise RuntimeError(f"No paper with arxiv id {arxiv_id}")
        with open(path, "wb") as f:  # noqa: ASYNC101
            f.write(await r.read())


async def xiv_to_pdf(doi, path, domain: str, session: ClientSession) -> None:
    async with session.get(
        f"https://{domain}/content/{doi}.full.pdf", allow_redirects=True
    ) as r:
        if r.ok and await likely_pdf(r):
            with open(path, "wb") as f:  # noqa: ASYNC101
                f.write(await r.read())
            return


async def link_to_pdf(url, path, session: ClientSession) -> None:
    # download
    async with session.get(url, allow_redirects=True) as r:
        r.raise_for_status()
        if "pdf" in r.headers["Content-Type"]:
            with open(path, "wb") as f:  # noqa: ASYNC101
                f.write(await r.read())
            return
        # try to find a pdf link
        html_text = await r.text()

    # I know this looks weird
    # I just need to try stuff and be able
    # to break out of flow if I find a pdf
    def get_pdf() -> str:
        # try for chemrxiv special tag
        pdf_link = re.search(
            r'content="(https://chemrxiv.org/engage/api-gateway/chemrxiv/assets.*\.pdf)"',
            html_text,
        )
        if pdf_link:
            return pdf_link.group(1)
        try:
            return search_pdf_link(html_text, epdf=True)
        except NoPDFLinkError:
            return search_pdf_link(html_text)

    try:
        pdf_link = get_pdf()
    except NoPDFLinkError as exc:
        raise RuntimeError(f"No PDF link found for {url}.") from exc
    # check if the link is relative
    if pdf_link.startswith("/"):
        pdf_link = get_scheme_hostname(url) + pdf_link

    try:
        async with session.get(pdf_link, allow_redirects=True) as r:
            r.raise_for_status()
            if "pdf" in r.headers["Content-Type"]:
                with open(path, "wb") as f:  # noqa: ASYNC101
                    f.write(await r.read())
                return
            raise RuntimeError(f"No PDF found from URL {pdf_link!r}.")
    except (TypeError, InvalidURL) as exc:
        raise RuntimeError(f"Malformed URL {pdf_link!r} from {url}.") from exc


async def find_pmc_pdf_link(pmc_id, session: ClientSession) -> str:
    url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}"
    async with session.get(url) as r:
        try:
            r.raise_for_status()
        except ClientResponseError as exc:
            raise RuntimeError(
                f"Failed to download PubMed Central ID {pmc_id} from URL {url}."
            ) from exc
        try:
            pdf_link = search_pdf_link(text=await r.text())
        except NoPDFLinkError as exc:
            raise RuntimeError(
                f"No PDF link matched for PubMed Central ID {pmc_id} from URL {url}."
            ) from exc
        return f"https://www.ncbi.nlm.nih.gov{pdf_link}"


async def pubmed_to_pdf(pubmed_id, path, session: ClientSession) -> None:
    async with session.get(f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/") as r:
        if not r.ok:
            raise RuntimeError(
                f"Error fetching PMC ID for PubMed ID {pubmed_id}. {r.status}"
            )
        html_text = await r.text()
        pmc_id_match = re.search(r"PMC\d+", html_text)
        if pmc_id_match is None:
            raise RuntimeError(f"No PMC ID found for PubMed ID {pubmed_id}.")
        pmc_id = pmc_id_match.group(0)
    pmc_id = pmc_id[3:]
    await pmc_to_pdf(pmc_id, path, session)


async def pmc_to_pdf(
    pmc_id: str, path: str | os.PathLike, session: ClientSession
) -> None:
    pdf_url = await find_pmc_pdf_link(pmc_id, session)
    async with session.get(pdf_url, allow_redirects=True) as r:
        cause_exc: Exception | None = None
        try:
            r.raise_for_status()
        except ClientResponseError as exc:
            cause_exc = exc
        if not await likely_pdf(r):
            cause_exc = ValueError("Not a PDF.")
        if cause_exc:
            raise RuntimeError(
                f"Failed to convert PubMed Central ID {pmc_id} to PDF given URL"
                f" {pdf_url}."
            ) from cause_exc
        with open(path, "wb") as f:  # noqa: ASYNC101
            f.write(await r.read())


async def arxiv_scraper(paper, path, session: ClientSession) -> bool:
    # check doi
    # example: 10.48550/arXiv.2305.10379
    if "DOI" in paper["externalIds"] and paper["externalIds"]["DOI"].split("/")[
        -1
    ].startswith("arXiv"):
        arxiv_id = paper["externalIds"]["DOI"].split("/arXiv.")[-1]
        await arxiv_to_pdf(arxiv_id, path, session)
        return True
    # check if it was somehow set
    if "ArXiv" in paper["externalIds"]:
        arxiv_id = paper["externalIds"]["ArXiv"]
        await arxiv_to_pdf(arxiv_id, path, session)
        return True
    return False


async def xiv_scraper(paper, path, domain: str, session: ClientSession) -> bool:
    if "DOI" not in paper["externalIds"]:
        return False
    doi = paper["externalIds"]["DOI"]
    # check if it has biorxiv/medrxiv prefix
    if not doi.startswith("10.1101/"):
        return False
    await xiv_to_pdf(doi, path, domain, session)
    return True


async def medrxiv_scraper(paper, path, session: ClientSession) -> bool:
    return await xiv_scraper(paper, path, "www.medrxiv.org", session)


async def biorxiv_scraper(paper, path, session: ClientSession) -> bool:
    return await xiv_scraper(paper, path, "www.biorxiv.org", session)


async def chemrxiv_scraper(paper, path, session: ClientSession) -> bool:
    if "DOI" not in paper["externalIds"]:
        return False
    doi = paper["externalIds"]["DOI"]
    # check if it has chemrxiv prefix
    if "chemrxiv" not in doi:
        return False
    # get resolved doi
    link = f"https://doi.org/{doi}"
    await link_to_pdf(link, path, session)
    return True


async def pmc_scraper(paper, path, session: ClientSession) -> bool:
    if "PubMedCentral" not in paper["externalIds"]:
        return False
    pmc_id = paper["externalIds"]["PubMedCentral"]
    await pmc_to_pdf(pmc_id, path, session)
    return True


async def pubmed_scraper(paper, path, session: ClientSession) -> bool:
    if "PubMed" not in paper["externalIds"]:
        return False
    pubmed_id = paper["externalIds"]["PubMed"]
    await pubmed_to_pdf(pubmed_id, path, session)
    return True


async def openaccess_scraper(paper, path, session: ClientSession) -> bool:
    # NOTE: paper may not have the key 'openAccessPdf', or its value may be None
    url = (paper.get("openAccessPdf") or {}).get("url")
    if not url:
        return False
    await link_to_pdf(url, path, session)
    return True


async def local_scraper(paper, path) -> bool:  # noqa: ARG001
    return True


def default_scraper(**scraper_kwargs) -> Scraper:
    scraper = Scraper(**scraper_kwargs)
    scraper.register_scraper(local_scraper, priority=12)
    scraper_rate_limit_config: dict[str, Any] = {
        "attach_session": True,
        "rate_limit": RateLimits.SCRAPER.value,
    }
    scraper.register_scraper(arxiv_scraper, **scraper_rate_limit_config)
    scraper.register_scraper(medrxiv_scraper, **scraper_rate_limit_config)
    scraper.register_scraper(biorxiv_scraper, **scraper_rate_limit_config)
    scraper.register_scraper(chemrxiv_scraper, **scraper_rate_limit_config)
    scraper.register_scraper(pmc_scraper, priority=9, **scraper_rate_limit_config)
    scraper.register_scraper(pubmed_scraper, priority=9, **scraper_rate_limit_config)
    scraper.register_scraper(
        openaccess_scraper, priority=9, **scraper_rate_limit_config
    )
    return scraper


async def parse_semantic_scholar_metadata(paper: dict[str, Any]) -> dict[str, Any]:
    """Parse raw paper metadata from Semantic Scholar into a richer format."""
    bibtex = paper["citationStyles"]["bibtex"]
    key = bibtex.split("{")[1].split(",")[0]
    return {
        "citation": format_bibtex(bibtex, key),
        "key": key,
        "bibtex": clean_upbibtex(bibtex),
        "tldr": paper.get("tldr"),
        "year": paper["year"],
        "url": paper["url"],
        "paperId": paper["paperId"],
        "doi": paper["externalIds"].get("DOI"),
        "citationCount": paper["citationCount"],
        "title": paper["title"],
    }


async def preprocess_google_scholar_metadata(  # noqa: C901
    paper: dict[str, Any], session: ClientSession
) -> dict[str, Any]:
    # get years
    match = year_extract_pattern.findall(paper["publication_info"]["summary"])
    year = match[0] if len(match) > 0 else None
    paper["year"] = year

    # set pdf link
    if "resources" in paper:
        for res in paper["resources"]:
            if "file_format" in res and res["file_format"] == "PDF":
                paper["openAccessPdf"] = {"url": res["link"]}
                break
            if "link" in res:
                paper["openAccessPdf"] = {"url": res["link"]}
                # do not break, we want to try to get a pdf link

    # did we get a link? If not, fallback onto given link
    if "openAccessPdf" not in paper and "link" in paper:
        paper["openAccessPdf"] = {"url": paper["link"]}

    # set external ids
    paper["externalIds"] = {}
    if "link" in paper:
        if paper["link"].startswith("https://arxiv.org/abs/"):
            paper["externalIds"]["ArXiv"] = paper["link"].split(
                "https://arxiv.org/abs/"
            )[1]

        doi = find_doi(paper["link"])
        if doi is not None:
            paper["externalIds"]["DOI"] = doi
    if "DOI" not in paper["externalIds"]:
        # Fall back to getting DOI from crossref
        author_query = []
        if "authors" in paper["publication_info"]:
            author_query = [a["name"] for a in paper["publication_info"]["authors"]]
        doi = await reconcile_doi(paper["title"], author_query, session)
        paper["externalIds"]["DOI"] = doi

    # set citation count
    paper["citationCount"] = (
        int(paper["inline_links"]["cited_by"]["total"])
        if (
            "cited_by" in paper["inline_links"]
            and paper["inline_links"]["cited_by"]["total"]
        )
        else 0  # best we can do
    )

    # set paperId to be hex digest of doi
    paper["paperId"] = encode_id(doi)  # type: ignore[arg-type]
    return paper


async def parallel_preprocess_google_scholar_metadata(
    papers: Iterable[dict[str, Any]],
    session: ClientSession,
    logger: logging.Logger | None = None,
) -> list[dict[str, Any]]:
    """
    Preprocess papers in parallel, discarding ones with preprocessing failures.

    NOTE: this function does not preserve the order of papers due to variable
    preprocessing times.
    """
    preprocessed_papers = []

    async def index(paper: dict[str, Any]) -> None:
        try:
            preprocessed_papers.append(
                await preprocess_google_scholar_metadata(paper, session)
            )
        except DOINotFoundError:
            if logger:
                logger.exception(f"Failed to find a DOI for paper {paper}.")

    await asyncio.gather(*(index(p) for p in papers))
    return preprocessed_papers


async def parse_google_scholar_metadata(
    paper: dict[str, Any], session: ClientSession
) -> dict[str, Any]:
    """Parse pre-processed paper metadata from Google Scholar into a richer format."""
    doi: str | None = (paper.get("externalIds") or {}).get("DOI")
    citation: str | None = None
    if doi:
        try:
            bibtex = await doi_to_bibtex(doi, session)
            key: str = bibtex.split("{")[1].split(",")[0]
            citation = format_bibtex(bibtex, key, clean=False)
        except DOINotFoundError:
            doi = None
        except CitationConversionError:
            citation = None
    if (not doi or not citation) and "inline_links" in paper:
        # get citation by following link
        # SLOW SLOW Using SerpAPI for this
        async with session.get(
            paper["inline_links"]["serpapi_cite_link"],
            params={"api_key": os.environ["SERPAPI_API_KEY"]},
        ) as r:
            # we raise here, because something really is wrong.
            r.raise_for_status()
            data = await r.json()
        citation = next(c["snippet"] for c in data["citations"] if c["title"] == "MLA")
        bibtex_link = next(c["link"] for c in data["links"] if c["name"] == "BibTeX")
        async with session.get(bibtex_link) as r:
            try:
                r.raise_for_status()
            except ClientResponseError as exc:
                # we may have a 443 - link expired
                msg = (
                    "Google scholar blocked"
                    if r.status == 443  # noqa: PLR2004
                    else "Unexpected failure to follow"
                )
                raise RuntimeError(
                    f"{msg} bibtex link {bibtex_link} for paper {paper}."
                ) from exc
            bibtex = await r.text()
            if not bibtex.strip().startswith("@"):
                raise RuntimeError(
                    f"Google scholar ip block bibtex link {bibtex_link} for paper"
                    f" {paper}."
                )
        key = bibtex.split("{")[1].split(",")[0]

    if not citation:
        raise RuntimeError(
            f"Exhausted all options for citation retrieval for {paper!r}"
        )
    return {
        "citation": citation,
        "key": key,
        "bibtex": bibtex,
        "year": paper["year"],
        "url": paper.get("link"),
        "paperId": paper["paperId"],
        "doi": paper["externalIds"].get("DOI"),
        "citationCount": paper["citationCount"],
        "title": paper["title"],
    }


async def reconcile_doi(title: str, authors: list[str], session: ClientSession) -> str:
    """
    Look up a DOI given a title and author list using Crossref.

    Raises:
        DOINotFoundError: If the reconciliation fails due to (1) Crossref API call had
            non-'ok' status code, (2) Crossref API response status indicates failure, or
            (3) Crossref response's entry had a low score.
    """
    # do not want initials
    authors_query = " ".join([a for a in authors if len(a) > 1])
    mailto = os.environ.get("CROSSREF_MAILTO", "paperscraper@example.org")
    # get DOI via crossref
    url = "https://api.crossref.org/works"
    params = {
        "query.title": title,
        "mailto": mailto,
        "select": "DOI,score",
        "rows": "1",
    }
    if authors_query:
        params["query.author"] = authors_query
    async with session.get(url, params=params, headers=crossref_headers()) as r:
        try:
            r.raise_for_status()
        except ClientResponseError as exc:
            raise DOINotFoundError("Could not reconcile DOI " + title) from exc
        data = await r.json()
        if data["status"] == "failed":
            raise DOINotFoundError(f"Could not find DOI for {title}")
        if (
            data["message"]["total-results"] == 0
            or data["message"]["items"][0]["score"] < 0.5  # noqa: PLR2004
        ):
            raise DOINotFoundError(f"Could not find DOI for {title}")
        return data["message"]["items"][0]["DOI"]


async def doi_to_bibtex(doi: str, session: ClientSession) -> str:
    # get DOI via crossref
    url = f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex"
    async with session.get(url, headers=crossref_headers()) as r:
        if not r.ok:
            raise DOINotFoundError(
                f"Per HTTP status code {r.status}, could not resolve DOI {doi}."
            )
        data = await r.text()
    # must make new key
    key = data.split("{")[1].split(",")[0]
    new_key = key.replace("_", "")
    try:
        author_frag = (
            data.split("author={")[1]
            .split("}")[0]
            .split()[0]
            .strip()
            .replace(" and ", "")
            .replace(",", "")
        )
        title_frag = data.split("title={")[1].split("}")[0].split()[0].strip()
        year_frag = data.split("year={")[1].split("}")[0].split()[0].strip()
    except IndexError:
        return data.replace(key, new_key)
    new_key = f"{author_frag}{year_frag}{title_frag}"
    return data.replace(key, new_key)


class RateLimits(float, Enum):
    """Rate limits (requests/sec) based on API provider."""

    SEMANTIC_SCHOLAR = 90.0
    GOOGLE_SCHOLAR = 1.0
    # SEE: https://www.crossref.org/documentation/metadata-plus/#00343
    CROSSREF = 30.0  # noqa: PIE796
    SCRAPER = 30 / 60
    FALLBACK_SLOW = 15 / 60


SEMANTIC_SCHOLAR_API_FIELDS: str = ",".join([
    "citationStyles",
    "externalIds",
    "url",
    "openAccessPdf",
    "year",
    "isOpenAccess",
    "influentialCitationCount",
    "citationCount",
    "title",
])
SEMANTIC_SCHOLAR_BASE_URL = "https://api.semanticscholar.org"


class SematicScholarSearchType(IntEnum):
    DEFAULT = auto()
    PAPER = auto()
    PAPER_RECOMMENDATIONS = auto()
    DOI = auto()
    FUTURE_CITATIONS = auto()
    PAST_REFERENCES = auto()
    GOOGLE = auto()

    def make_url_params(  # noqa: PLR0911
        self,
        params: dict[str, Any],
        query: str,
        offset: int,
        limit: int,
        include_base_url: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        """
        Make the target URL and in-place update the input URL parameters.

        Args:
            params: URL parameters to in-place update.
            query: Either a search query or a Semantic Scholar paper ID.
            offset: Offset to place in the URL parameters for the default search type.
            limit: Limit to place in the URL parameters for some search types.
            include_base_url: Set True (default) to include the base URL.

        Returns:
            Two-tuple of URL and URL parameters.
        """
        base = SEMANTIC_SCHOLAR_BASE_URL if include_base_url else ""
        if self == SematicScholarSearchType.DEFAULT:
            params["query"] = query.replace("-", " ")
            params["offset"] = offset
            params["limit"] = limit
            return f"{base}/graph/v1/paper/search", params
        if self == SematicScholarSearchType.PAPER:
            return f"{base}/graph/v1/paper/{query}", params
        if self == SematicScholarSearchType.PAPER_RECOMMENDATIONS:
            return f"{base}/recommendations/v1/papers/forpaper/{query}", params
        if self == SematicScholarSearchType.DOI:
            return f"{base}/graph/v1/paper/DOI:{query}", params
        if self == SematicScholarSearchType.FUTURE_CITATIONS:
            params["limit"] = limit
            return f"{base}/graph/v1/paper/{query}/citations", params
        if self == SematicScholarSearchType.PAST_REFERENCES:
            params["limit"] = limit
            return f"{base}/graph/v1/paper/{query}/references", params
        if self == SematicScholarSearchType.GOOGLE:
            params["limit"] = 1
            return f"{base}/graph/v1/paper/search", params
        raise NotImplementedError


# The fact that 20 is actually the max value was not in the SERP API docs as
# of 4/15/2024, but was determined by contacting SERP support
GOOGLE_SEARCH_MAX_PAGE_SIZE = 20

async def a_search_papers(  # noqa: C901, PLR0912, PLR0915
    query: str,
    limit: int = 10,
    pdir: str | os.PathLike = os.curdir,
    semantic_scholar_api_key: str | None = None,
    serp_api_key: str | None = None,
    _paths: dict[str | os.PathLike, dict[str, Any]] | None = None,
    _limit: int = 100,
    _offset: int = 0,
    logger: logging.Logger | None = None,
    year: str | None = None,
    verbose: bool = False,
    scraper: Scraper | None = None,
    batch_size: int = 10,
    search_type: str = "google",#default google
) -> dict[str, dict[str, Any]]:
    """
    Asynchronously search for papers using Semantic Scholar, and scrape them.

    Args:
        query: Search input, its exact meaning depends on the search_type.
        limit: Target result count, we will try to give at least this many results.
            However, for cases when Semantic Scholar doesn't give enough results,
            there will be less than this value.
        pdir: Optional directory (created if it does not exist), that defaults to the
            current directory, passed to Scraper.batch_scrape's paper_file_dump_dir.
        semantic_scholar_api_key: Optional Semantic Scholar API key, otherwise
            attempt to pull it from the environment variable SEMANTIC_SCHOLAR_API_KEY.
        _paths: Previous Scraper.batch_scrape, used internally for recursion.
        _limit: Result limit to pass to the Semantic Scholar API, only relevant for
            some search_type.
        _offset: Offset in the search results, used internally for recursion.
        logger: Optional logger to use for logging. If left as default of None,
            a 'paper-scraper' logger at ERROR level will be used.
        year: Optional year string, either a single year (e.g. '2019')
            or a year range (e.g. '2019-2023').
        verbose: Set True to colorized log to stderr at DEBUG level.
        scraper: Optional scraper to use after searching. If left as default of None,
            the default scraper will be created.
        batch_size: Passed through to Scraper.batch_scrape's batch_size.
        search_type: Lowercase string corresponding with a SematicScholarSearchType key.

    Returns:
        Dict union of all Scraper.batch_scrape outputs.
    """
    #修改处
    pdir = Path(pdir)
    print(pdir)
    pdir.mkdir(parents=True, exist_ok=True)

    if logger is None:
        logger = logging.getLogger("paper-scraper")
        logger.setLevel(logging.ERROR)
        if verbose:
            logger.setLevel(logging.DEBUG)
            ch = logging.StreamHandler()
            ch.setFormatter(CustomFormatter())
            logger.addHandler(ch)
    params = {"fields": SEMANTIC_SCHOLAR_API_FIELDS}
    if _limit > 100:  # noqa: PLR2004
        raise NotImplementedError("Didn't handle Semantic Scholar pagination ('next').")
    rate_limit: float = RateLimits.FALLBACK_SLOW.value
    endpoint, params = SematicScholarSearchType[search_type.upper()].make_url_params(
        params, query, _offset, _limit
    )
    if search_type == "google":
        # SEE: https://serpapi.com/google-scholar-api
        google_endpoint = "https://serpapi.com/search.json"
        google_params = {
            "q": query,
            "api_key": serp_api_key,
            "engine": "google_scholar",
            "num": GOOGLE_SEARCH_MAX_PAGE_SIZE,
            "start": _offset,
            # TODO - add offset and limit here  # noqa: TD004
        }
        rate_limit = RateLimits.GOOGLE_SCHOLAR.value
    elif search_type == "paper":
        raise NotImplementedError(
            f"Only added 'paper' search type to {SematicScholarSearchType.__name__},"
            " but not yet to this function in general."
        )

    if year is not None and search_type == "default":
        # need to really make sure year is correct
        year = year.strip()
        if "-" in year:
            # make sure start/end are valid
            with contextlib.suppress(ValueError):
                start, end = year.split("-")
                if int(start) <= int(end):
                    params["year"] = year
        if "year" not in params:
            logger.warning(f"Could not parse year {year}")

    if year is not None and search_type == "google":
        # need to really make sure year is correct
        year = year.strip()
        if "-" in year:
            # make sure start/end are valid
            try:
                start, end = year.split("-")
                if int(start) <= int(end):
                    google_params["as_ylo"] = start
                    google_params["as_yhi"] = end
            except ValueError:
                pass
        else:
            with contextlib.suppress(ValueError):
                google_params["as_ylo"] = year
                google_params["as_yhi"] = year
        if "as_ylo" not in google_params:
            logger.warning(f"Could not parse year {year}")

    paths: dict[str, dict[str, Any]] = (
        {str(k): v for k, v in _paths.items()} if _paths is not None else {}
    )
    scraper = scraper or default_scraper()
    ssheader = get_header()
    if semantic_scholar_api_key is not None:
        ssheader["x-api-key"] = semantic_scholar_api_key
        rate_limit = RateLimits.SEMANTIC_SCHOLAR.value
    else:
        # check if it's in the environment
        with contextlib.suppress(KeyError):
            ssheader["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
            rate_limit = RateLimits.SEMANTIC_SCHOLAR.value
    async with ThrottledClientSession(
        rate_limit=rate_limit, headers=ssheader
    ) as ss_session:
        async with ss_session.get(
            url=google_endpoint if search_type == "google" else endpoint,
            params=google_params if search_type == "google" else params,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as exc:
                if response.status == 404 and search_type == "doi":  # noqa: PLR2004
                    raise DOINotFoundError(f"DOI {query} not found.") from exc
                raise RuntimeError(
                    f"Error searching papers given query {query}."
                ) from exc
            data = await response.json()
        if search_type == "default":
            has_more_data = _offset + _limit < data["total"]
        elif search_type == "google":
            if "organic_results" not in data:
                return paths
            has_more_data = "pagination" in data
            papers = data["organic_results"]
            titles = [p["title"] for p in papers]
            years: list[str | None] = [None] * len(papers)
            for i, p in enumerate(papers):
                match = year_extract_pattern.findall(p["publication_info"]["summary"])
                if len(match) > 0:
                    years[i] = match[0]

            # get PDF resources
            google_pdf_links: list[str | None] = [None] * len(papers)
            for i, p in enumerate(papers):
                if "resources" in p:
                    for res in p["resources"]:
                        if res.get("file_format") == "PDF":
                            google_pdf_links[i] = res["link"]

            # want this separate, since ss is rate_limit for Google
            async with ThrottledClientSession(
                rate_limit=rate_limit, headers=ssheader
            ) as ss_sub_session:
                # Now we need to reconcile with S2 API these results
                async def google2s2(
                    title: str, year: str | None, pdf_link
                ) -> dict[str, Any] | None:
                    local_p = params.copy()
                    local_p["query"] = title.replace("-", " ")
                    if year is not None:
                        local_p["year"] = year
                    async with ss_sub_session.get(
                        url=endpoint, params=local_p
                    ) as response:
                        if not response.ok:
                            logger.warning(
                                "Error correlating papers from google to semantic"
                                f" scholar: status {response.status}, reason"
                                f" {response.reason!r}, text {await response.text()!r}."
                            )
                            return None
                        response_data = await response.json()
                    if (
                        "data" not in response_data
                        and year is not None
                        and response_data["total"] == 0
                    ):
                        logger.info(
                            f"{title} | {year} not found. Now trying without year"
                        )
                        del local_p["year"]
                        async with ss_sub_session.get(
                            url=endpoint, params=local_p
                        ) as resp:
                            if not resp.ok:
                                logger.warning(
                                    "Error correlating papers from google"
                                    " to semantic scholar (no year):"
                                    f" status {resp.status}, reason {resp.reason},"
                                    f" text {await resp.text()!r}."
                                )
                            response_data = await resp.json()
                    if "data" in response_data:
                        if pdf_link is not None:
                            # Google Scholar url takes precedence
                            response_data["data"][0]["openAccessPdf"] = {
                                "url": pdf_link
                            }
                        return response_data["data"][0]
                    return None

                responses = await asyncio.gather(*(
                    google2s2(t, y, p)
                    for t, y, p in zip(titles, years, google_pdf_links, strict=True)
                ))
            data = {"data": [r for r in responses if r is not None]}
            data["total"] = len(data["data"])
        field = "data"
        if search_type == "paper_recommendations":
            field = "recommendedPapers"
        elif search_type == "doi":
            data = {"data": [data]}
        if field not in data:
            return paths
        papers = data[field]
        if search_type == "future_citations":
            papers = [p["citingPaper"] for p in papers]
        if search_type == "past_references":
            papers = [p["citedPaper"] for p in papers]
        # resort based on influentialCitationCount - is this good?
        if search_type == "default":
            papers.sort(key=lambda x: x["influentialCitationCount"], reverse=True)
        if search_type in ["default", "google"]:
            logger.info(
                f"Found {data['total']} papers, analyzing {_offset} to"
                f" {_offset + len(papers)}"
            )

        # batch them, since we may reach desired limit before all done
        paths.update(
            await scraper.batch_scrape(
                papers,
                paper_file_dump_dir=pdir,
                paper_parser=parse_semantic_scholar_metadata,
                batch_size=batch_size,
                limit=limit,
                logger=logger,
            )
        )
    if search_type in ["default", "google"] and len(paths) < limit and has_more_data:
        try:
            result = await a_search_papers(
                query,
                limit=limit,
                pdir=pdir,
                semantic_scholar_api_key=semantic_scholar_api_key,
                serp_api_key=serp_api_key,
                _paths=paths,  # type: ignore[arg-type]
                _limit=_limit,
                _offset=_offset + (GOOGLE_SEARCH_MAX_PAGE_SIZE if search_type == "google" else _limit),
                logger=logger,
                year=year,
                verbose=verbose,
                scraper=scraper,
                batch_size=batch_size,
                search_type=search_type,
            )
            paths.update(result)  # 更新 paths
        except Exception as e:
            if logger is not None:
                logger.exception(f"An error occurred: {e}")

    if _offset == 0:
        await scraper.close()
    return paths



async def a_gsearch_papers(  # noqa: C901
    query: str,
    limit: int = 10,
    pdir: str | os.PathLike = os.curdir,
    _paths: dict[str | os.PathLike, dict[str, Any]] | None = None,
    _offset: int = 0,
    _limit: int = GOOGLE_SEARCH_MAX_PAGE_SIZE,
    logger: logging.Logger | None = None,
    year: str | None = None,
    verbose: bool = False,
    scraper: Scraper | None = None,
    batch_size: int = 10,
) -> dict[str, dict[str, Any]]:
    pdir = Path(pdir)
    pdir.mkdir(exist_ok=True)
    if logger is None:
        logger = logging.getLogger("paper-scraper")
        logger.setLevel(logging.ERROR)
        if verbose:
            logger.setLevel(logging.DEBUG)
            ch = logging.StreamHandler()
            ch.setFormatter(CustomFormatter())
            logger.addHandler(ch)
    # SEE: https://serpapi.com/google-scholar-api
    endpoint = "https://serpapi.com/search.json"
    # adjust _limit if limit is smaller (with margin for scraping errors)
    # for example, if limit is 3 we would be fine only getting 8 results
    # but if limit is 50, this will just return normal default _limit (20)
    _limit = min(_limit, limit + 5)
    params = {
        "q": query,
        "api_key": os.environ["SERPAPI_API_KEY"],
        "engine": "google_scholar",
        "num": _limit,
        "start": _offset,
    }

    if year is not None:
        # need to really make sure year is correct
        year = year.strip()
        if "-" in year:
            # make sure start/end are valid
            try:
                start, end = year.split("-")
                if int(start) <= int(end):
                    params["as_ylo"] = start
                    params["as_yhi"] = end
            except ValueError:
                pass
        else:
            with contextlib.suppress(ValueError):
                params["as_ylo"] = year
                params["as_yhi"] = year
        if "as_ylo" not in params:
            logger.warning(f"Could not parse year {year}")

    paths: dict[str, dict[str, Any]] = (
        {str(k): v for k, v in _paths.items()} if _paths is not None else {}
    )
    scraper = scraper or default_scraper()

    async with ThrottledClientSession(
        headers=get_header(),
        rate_limit=RateLimits.GOOGLE_SCHOLAR.value,  # Share rate limits between gs/crossref
    ) as session:
        async with session.get(
            url=endpoint,
            params=params,
        ) as response:
            if not response.ok:
                raise RuntimeError(
                    "Error searching papers:"
                    f" {response.status} {response.reason} {await response.text()}"
                )
            data = await response.json()

        if "organic_results" not in data:
            return paths
        papers = data["organic_results"]
        total_papers = data["search_information"].get("total_results", 1)
        logger.info(
            f"Found {total_papers} papers, analyzing {_offset} to"
            f" {_offset + len(papers)}"
        )

        # batch them, since we may reach desired limit before all done
        paths.update(
            await scraper.batch_scrape(
                # we only process papers that have a link and a DOI
                await parallel_preprocess_google_scholar_metadata(
                    papers, session, logger
                ),
                paper_file_dump_dir=pdir,
                paper_parser=partial(parse_google_scholar_metadata, session=session),
                batch_size=batch_size,
                limit=limit,
                logger=logger,
            )
        )
    if len(paths) < limit and _offset + _limit < total_papers:
        paths.update(
            await a_gsearch_papers(
                query,
                limit=limit,
                pdir=pdir,
                _paths=paths,  # type: ignore[arg-type]
                _offset=_offset + limit,
                _limit=_limit,
                logger=logger,
                year=year,
                verbose=verbose,
                scraper=scraper,
                batch_size=batch_size,
            )
        )
    await scraper.close()
    return paths


def search_papers(*a_search_args, **a_search_kwargs):
    # special case for jupyter notebooks
    if "get_ipython" in globals() or "google.colab" in sys.modules:
        import nest_asyncio

        nest_asyncio.apply()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as e:  # noqa: F841
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    #添加的逻辑，保证健壮性    
    # try:
    return loop.run_until_complete(a_search_papers(*a_search_args, **a_search_kwargs))
    # except Exception as e:
        # logging.error(f"An unexpected error occurred: {e}")
        # return {"error": "An unexpected error occurred. Please try again later."}
        
    #     if not loop.is_running():
    #         loop.close()
