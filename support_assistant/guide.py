"""Download the markdown user guide from GitHub, split it into sections and index it."""

from __future__ import annotations

import io
import re
import tarfile
from dataclasses import dataclass
from pathlib import PurePosixPath

import httpx
from django.conf import settings
from django.contrib.postgres.search import SearchVector
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from support_assistant.exceptions import GuideFetchError
from support_assistant.models import GuideChunk

GITHUB_API_URL = "https://api.github.com"
MARKDOWN_EXTENSIONS = (".md", ".md.erb")
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_CHUNK_CHARS = 2000
MAX_HEADING_LEVEL = 3

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
CUSTOM_ANCHOR_RE = re.compile(r"\s*\{#([\w-]+)\}\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Section:
    """A section of a guide page, ready to be stored as a ``GuideChunk``."""

    page_title: str
    heading: str
    url: str
    content: str


@dataclass(frozen=True)
class SyncResult:
    files: int
    created: int
    updated: int
    deleted: int


def slugify_heading(text: str) -> str:
    """Build a GitHub-style anchor slug from a heading."""
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"\s", "-", text)


def page_url(base_url: str, relative_path: str, suffix: str) -> str:
    """Build the published URL for a guide file from its path relative to the guide root.

    ``getting-started.html.md.erb`` becomes ``<base>/getting-started.html`` and
    ``keys/index.md`` becomes ``<base>/keys/``.
    """
    path = relative_path
    for extension in (".erb", ".md", ".html"):
        path = path.removesuffix(extension)
    parent, _, name = path.rpartition("/")
    if name != "index":
        return f"{base_url.rstrip('/')}/{path}{suffix}"
    path = f"{parent}/" if parent else ""
    return f"{base_url.rstrip('/')}/{path}"


def _strip_front_matter(text: str) -> tuple[str, str | None]:
    """Remove YAML front matter, returning the body and any ``title`` it declares."""
    if not text.startswith("---"):
        return text, None
    lines = text.splitlines()
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            title = None
            for meta in lines[1:index]:
                key, _, value = meta.partition(":")
                if key.strip() == "title" and value.strip():
                    title = value.strip().strip("\"'")
            return "\n".join(lines[index + 1 :]), title
    return text, None


def _split_long(content: str) -> list[str]:
    """Split content into parts of at most ``MAX_CHUNK_CHARS``, on paragraph boundaries."""
    parts: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", content):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) + 2 > MAX_CHUNK_CHARS:
            parts.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}" if current else paragraph
        while len(current) > MAX_CHUNK_CHARS:
            parts.append(current[:MAX_CHUNK_CHARS])
            current = current[MAX_CHUNK_CHARS:]
    if current:
        parts.append(current)
    return parts


def split_markdown(text: str, url: str, fallback_title: str) -> list[Section]:
    """Split a markdown page into sections at level 1-3 headings.

    Content before the first heading belongs to the page itself. Headings inside fenced code
    blocks are ignored, and duplicate anchors are de-duplicated GitHub-style (``-1``, ``-2``).
    """
    body, title = _strip_front_matter(text)
    page_title = title or fallback_title

    raw_sections: list[tuple[str, str, list[str]]] = []
    heading, anchor_url, lines = page_title, url, []
    seen_anchors: dict[str, int] = {}
    in_fence = False
    first_heading = True

    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
        match = None if in_fence else HEADING_RE.match(line)
        if not match or len(match.group(1)) > MAX_HEADING_LEVEL:
            lines.append(line)
            continue

        raw_sections.append((heading, anchor_url, lines))
        text_heading = match.group(2)
        custom = CUSTOM_ANCHOR_RE.search(text_heading)
        if custom:
            text_heading = text_heading[: custom.start()]
        anchor = custom.group(1) if custom else slugify_heading(text_heading)
        count = seen_anchors.get(anchor, 0)
        seen_anchors[anchor] = count + 1
        if count:
            anchor = f"{anchor}-{count}"

        level = len(match.group(1))
        if level == 1 and first_heading and not title:
            page_title = text_heading
        first_heading = False
        heading = text_heading
        anchor_url = url if level == 1 else f"{url}#{anchor}"
        lines = []
    raw_sections.append((heading, anchor_url, lines))

    sections = []
    for section_heading, section_url, section_lines in raw_sections:
        for part in _split_long("\n".join(section_lines)):
            sections.append(
                Section(
                    page_title=page_title,
                    heading=section_heading,
                    url=section_url,
                    content=part,
                )
            )
    return sections


class GitHubGuideSource:
    """Downloads markdown files from a GitHub repository as a single tarball."""

    def __init__(
        self,
        repo: str,
        ref: str,
        path: str = "",
        token: str | None = None,
        timeout: float = 60.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.repo = repo
        self.ref = ref
        self.path = path.strip("/")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(
            base_url=GITHUB_API_URL,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    @classmethod
    def from_settings(cls) -> GitHubGuideSource:
        if not settings.SUPPORT_ASSISTANT_GUIDE_REPO:
            raise ImproperlyConfigured("SUPPORT_ASSISTANT_GUIDE_REPO must be configured")
        return cls(
            repo=settings.SUPPORT_ASSISTANT_GUIDE_REPO,
            ref=settings.SUPPORT_ASSISTANT_GUIDE_REF,
            path=settings.SUPPORT_ASSISTANT_GUIDE_PATH,
            token=settings.SUPPORT_ASSISTANT_GITHUB_TOKEN,
        )

    def close(self) -> None:
        self._client.close()

    def _download(self) -> bytes:
        try:
            with self._client.stream("GET", f"/repos/{self.repo}/tarball/{self.ref}") as response:
                if response.is_error:
                    response.read()
                    raise GuideFetchError(
                        f"GitHub returned {response.status_code} for {self.repo}@{self.ref}"
                    )
                buffer = bytearray()
                for data in response.iter_bytes():
                    buffer.extend(data)
                    if len(buffer) > MAX_ARCHIVE_BYTES:
                        raise GuideFetchError("User guide archive exceeds the size limit")
                return bytes(buffer)
        except httpx.HTTPError as error:
            raise GuideFetchError(f"Failed to download user guide: {error}") from error

    def fetch_files(self) -> dict[str, str]:
        """Return markdown file contents keyed by path relative to the guide folder."""
        archive = self._download()
        prefix = f"{self.path}/" if self.path else ""
        files: dict[str, str] = {}
        try:
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    # Tarballs from GitHub wrap everything in an "<owner>-<repo>-<sha>/" folder
                    _, _, repo_path = member.name.partition("/")
                    if not repo_path.startswith(prefix) or not repo_path.endswith(
                        MARKDOWN_EXTENSIONS
                    ):
                        continue
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        continue
                    relative = str(PurePosixPath(repo_path[len(prefix) :]))
                    files[relative] = extracted.read().decode("utf-8", errors="replace")
        except tarfile.TarError as error:
            raise GuideFetchError(f"Could not read user guide archive: {error}") from error
        return files


def build_sections(files: dict[str, str], base_url: str, suffix: str) -> dict[str, list[Section]]:
    """Split every guide file into sections, keyed by file path."""
    sections = {}
    for path, text in sorted(files.items()):
        fallback_title = PurePosixPath(path).name.split(".")[0].replace("-", " ").capitalize()
        sections[path] = split_markdown(text, page_url(base_url, path, suffix), fallback_title)
    return sections


@transaction.atomic
def store_sections(sections_by_path: dict[str, list[Section]]) -> SyncResult:
    """Upsert guide sections and delete chunks that no longer exist in the guide."""
    existing = {
        (chunk.source_path, chunk.position): chunk
        for chunk in GuideChunk.objects.select_for_update()
    }
    fields = ("page_title", "heading", "url", "content")
    to_create, to_update, seen = [], [], set()

    for path, sections in sections_by_path.items():
        for position, section in enumerate(sections):
            key = (path, position)
            seen.add(key)
            chunk = existing.get(key)
            if chunk is None:
                to_create.append(GuideChunk(source_path=path, position=position, **vars(section)))
            elif any(getattr(chunk, field) != getattr(section, field) for field in fields):
                for field in fields:
                    setattr(chunk, field, getattr(section, field))
                chunk.updated_at = timezone.now()
                to_update.append(chunk)

    stale = [chunk.pk for key, chunk in existing.items() if key not in seen]
    GuideChunk.objects.filter(pk__in=stale).delete()
    created = GuideChunk.objects.bulk_create(to_create)
    GuideChunk.objects.bulk_update(to_update, [*fields, "updated_at"])

    changed = [chunk.pk for chunk in [*created, *to_update]]
    GuideChunk.objects.filter(pk__in=changed).update(
        search_vector=(
            SearchVector("page_title", weight="A", config="english")
            + SearchVector("heading", weight="A", config="english")
            + SearchVector("content", weight="B", config="english")
        )
    )
    return SyncResult(
        files=len(sections_by_path),
        created=len(to_create),
        updated=len(to_update),
        deleted=len(stale),
    )


def sync_user_guide(source: GitHubGuideSource) -> SyncResult:
    """Fetch the guide from GitHub and update the search index."""
    if not settings.SUPPORT_ASSISTANT_GUIDE_BASE_URL:
        raise ImproperlyConfigured("SUPPORT_ASSISTANT_GUIDE_BASE_URL must be configured")
    files = source.fetch_files()
    if not files:
        # Refuse to wipe the index if the repo, ref or path is wrong
        raise GuideFetchError("No markdown files found; check the guide repo, ref and path")
    sections = build_sections(
        files,
        settings.SUPPORT_ASSISTANT_GUIDE_BASE_URL,
        settings.SUPPORT_ASSISTANT_GUIDE_URL_SUFFIX,
    )
    return store_sections(sections)
