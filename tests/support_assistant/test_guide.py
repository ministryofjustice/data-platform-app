import io
import tarfile

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from support_assistant.exceptions import GuideFetchError
from support_assistant.guide import (
    MAX_CHUNK_CHARS,
    GitHubGuideSource,
    Section,
    build_sections,
    page_url,
    slugify_heading,
    split_markdown,
    store_sections,
    sync_user_guide,
)
from support_assistant.models import GuideChunk


def make_tarball(files: dict[str, str], root="ministryofjustice-test-user-guide-abc123"):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        directory = tarfile.TarInfo(root)
        directory.type = tarfile.DIRTYPE
        tar.addfile(directory)
        for path, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{root}/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def build_source(handler, path="source", token=None):
    client = httpx.Client(
        base_url="https://api.github.test", transport=httpx.MockTransport(handler)
    )
    return GitHubGuideSource(
        repo="ministryofjustice/test-user-guide", ref="main", path=path, token=token, client=client
    )


class TestSlugifyHeading:
    def test_lowercases_and_hyphenates(self):
        assert slugify_heading("Create an API key") == "create-an-api-key"

    def test_removes_punctuation(self):
        assert slugify_heading("What's a model? (beta)") == "whats-a-model-beta"


class TestPageUrl:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("getting-started.html.md.erb", "https://guide.test/getting-started.html"),
            ("keys/create.md", "https://guide.test/keys/create.html"),
            ("keys/index.md", "https://guide.test/keys/"),
            ("index.html.md.erb", "https://guide.test/"),
        ],
    )
    def test_builds_published_url(self, path, expected):
        assert page_url("https://guide.test/", path, ".html") == expected

    def test_uses_suffix(self):
        assert page_url("https://guide.test", "keys.md", "/") == "https://guide.test/keys/"


class TestSplitMarkdown:
    def test_splits_on_headings_with_anchor_urls(self):
        text = "# Keys\n\nIntro text.\n\n## Create a key\n\nDo this.\n\n### Rotate\n\nDo that."

        sections = split_markdown(text, "https://guide.test/keys.html", "Fallback")

        assert sections == [
            Section("Keys", "Keys", "https://guide.test/keys.html", "Intro text."),
            Section(
                "Keys", "Create a key", "https://guide.test/keys.html#create-a-key", "Do this."
            ),
            Section("Keys", "Rotate", "https://guide.test/keys.html#rotate", "Do that."),
        ]

    def test_uses_front_matter_title_and_content_before_first_heading(self):
        text = '---\ntitle: "Getting started"\nweight: 1\n---\nWelcome.\n\n## Sign in\n\nUse SSO.'

        sections = split_markdown(text, "https://guide.test/start.html", "Fallback")

        assert [(s.page_title, s.heading, s.content) for s in sections] == [
            ("Getting started", "Getting started", "Welcome."),
            ("Getting started", "Sign in", "Use SSO."),
        ]

    def test_uses_fallback_title_without_heading_or_front_matter(self):
        sections = split_markdown("Just text.", "https://guide.test/x.html", "Fallback")

        assert sections == [
            Section("Fallback", "Fallback", "https://guide.test/x.html", "Just text.")
        ]

    def test_ignores_headings_in_code_fences_and_deep_headings(self):
        text = "## Example\n\n```bash\n# not a heading\n```\n\n#### Detail\n\nMore."

        sections = split_markdown(text, "https://guide.test/x.html", "X")

        assert len(sections) == 1
        assert "# not a heading" in sections[0].content
        assert "#### Detail" in sections[0].content

    def test_deduplicates_anchors_and_supports_custom_anchors(self):
        text = "## Usage\n\nA\n\n## Usage\n\nB\n\n## Limits {#rate-limits}\n\nC"

        urls = [s.url for s in split_markdown(text, "https://guide.test/x.html", "X")]

        assert urls == [
            "https://guide.test/x.html#usage",
            "https://guide.test/x.html#usage-1",
            "https://guide.test/x.html#rate-limits",
        ]

    def test_splits_long_sections(self):
        paragraph = "word " * 300
        text = "## Long\n\n" + "\n\n".join([paragraph] * 5) + "\n\n" + "x" * (MAX_CHUNK_CHARS * 2)

        sections = split_markdown(text, "https://guide.test/x.html", "X")

        assert len(sections) > 1
        assert all(len(s.content) <= MAX_CHUNK_CHARS for s in sections)
        assert {s.heading for s in sections} == {"Long"}

    def test_unterminated_front_matter_is_kept(self):
        sections = split_markdown("---\ntitle: x", "https://guide.test/x.html", "X")

        assert sections[0].page_title == "X"


class TestGitHubGuideSource:
    def test_fetches_markdown_files_under_path(self):
        archive = make_tarball(
            {
                "source/index.html.md.erb": "# Home",
                "source/keys/create.md": "# Create",
                "source/images/logo.png": "png",
                "README.md": "# Readme",
            }
        )

        def handler(request):
            assert request.url.path == "/repos/ministryofjustice/test-user-guide/tarball/main"
            return httpx.Response(200, content=archive)

        files = build_source(handler).fetch_files()

        assert files == {"index.html.md.erb": "# Home", "keys/create.md": "# Create"}

    def test_fetches_whole_repo_without_path(self):
        archive = make_tarball({"README.md": "# Readme"})

        files = build_source(lambda request: httpx.Response(200, content=archive), path="")

        assert files.fetch_files() == {"README.md": "# Readme"}

    def test_sends_token_when_configured(self):
        source = GitHubGuideSource(repo="o/r", ref="main", token="ghp_test")  # gitleaks:allow

        assert source._client.headers["Authorization"] == "Bearer ghp_test"
        source.close()

    def test_raises_on_error_response(self):
        source = build_source(lambda request: httpx.Response(404, text="Not Found"))

        with pytest.raises(GuideFetchError, match="404"):
            source.fetch_files()

    def test_raises_on_transport_error(self):
        def handler(request):
            raise httpx.ConnectError("boom")

        with pytest.raises(GuideFetchError, match="boom"):
            build_source(handler).fetch_files()

    def test_raises_on_invalid_archive(self):
        source = build_source(lambda request: httpx.Response(200, content=b"not a tarball"))

        with pytest.raises(GuideFetchError, match="archive"):
            source.fetch_files()

    def test_raises_when_archive_too_large(self, monkeypatch):
        monkeypatch.setattr("support_assistant.guide.MAX_ARCHIVE_BYTES", 10)
        source = build_source(lambda request: httpx.Response(200, content=b"x" * 100))

        with pytest.raises(GuideFetchError, match="size limit"):
            source.fetch_files()

    def test_from_settings_requires_repo(self, settings):
        settings.SUPPORT_ASSISTANT_GUIDE_REPO = ""

        with pytest.raises(ImproperlyConfigured):
            GitHubGuideSource.from_settings()

    def test_from_settings(self):
        source = GitHubGuideSource.from_settings()

        assert (source.repo, source.ref, source.path) == (
            "ministryofjustice/test-user-guide",
            "main",
            "source",
        )
        source.close()


class TestBuildSections:
    def test_derives_fallback_title_from_file_name(self):
        sections = build_sections({"api-keys.md": "Some text."}, "https://guide.test", ".html")

        assert sections["api-keys.md"][0].page_title == "Api keys"
        assert sections["api-keys.md"][0].url == "https://guide.test/api-keys.html"


@pytest.mark.django_db
class TestStoreSections:
    def section(self, heading, content="Content"):
        return Section("Page", heading, f"https://guide.test/p.html#{heading}", content)

    def test_creates_indexed_chunks(self):
        result = store_sections({"p.md": [self.section("one"), self.section("two")]})

        assert (result.created, result.updated, result.deleted) == (2, 0, 0)
        assert GuideChunk.objects.filter(search_vector__isnull=False).count() == 2

    def test_updates_changed_skips_unchanged_and_prunes_stale(self):
        store_sections(
            {
                "p.md": [self.section("one"), self.section("two"), self.section("three")],
                "old.md": [self.section("old")],
            }
        )

        result = store_sections({"p.md": [self.section("one"), self.section("two", "Changed")]})

        assert (result.files, result.created, result.updated, result.deleted) == (1, 0, 1, 2)
        assert list(GuideChunk.objects.values_list("heading", "content")) == [
            ("one", "Content"),
            ("two", "Changed"),
        ]


@pytest.mark.django_db
class TestSyncUserGuide:
    def test_syncs_files_from_github(self):
        archive = make_tarball({"source/keys.md": "# Keys\n\n## Create\n\nChoose create key."})
        source = build_source(lambda request: httpx.Response(200, content=archive))

        result = sync_user_guide(source)

        assert result.created == 1
        chunk = GuideChunk.objects.get()
        assert chunk.url == "https://user-guide.test/keys.html#create"

    def test_refuses_to_prune_when_no_files_found(self, make_chunk):
        make_chunk("Existing", "Keep me")
        archive = make_tarball({"README.md": "# Readme"})
        source = build_source(lambda request: httpx.Response(200, content=archive))

        with pytest.raises(GuideFetchError, match="No markdown files"):
            sync_user_guide(source)

        assert GuideChunk.objects.count() == 1

    def test_requires_base_url(self, settings):
        settings.SUPPORT_ASSISTANT_GUIDE_BASE_URL = ""

        with pytest.raises(ImproperlyConfigured):
            sync_user_guide(build_source(lambda request: httpx.Response(500)))
