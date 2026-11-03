"""A fake embedding provider for tests: similarities come from a table, never from a model."""


class FakeEmbeddingProvider:
    """`table` maps (query, catalog text) to a similarity; any other pair is 0.

    `fail` (an exception) is raised by `build_index`, or by searches when `fail_on="search"`.
    Records the texts of every index built and the queries of every search.
    """

    model_id = "fake-embedder"

    def __init__(self, table=None, fail=None, fail_on="build"):
        self.table = dict(table or {})
        self.fail = fail
        self.fail_on = fail_on
        self.builds = []
        self.searches = []

    def build_index(self, texts):
        if self.fail is not None and self.fail_on == "build":
            raise self.fail
        self.builds.append(list(texts))
        return FakeTextIndex(self, list(texts))


class FakeTextIndex:
    def __init__(self, provider, texts):
        self.provider = provider
        self.texts = texts

    def similarities(self, queries):
        if self.provider.fail is not None and self.provider.fail_on == "search":
            raise self.provider.fail
        self.provider.searches.append(list(queries))
        return [[self.provider.table.get((query, text), 0.0) for text in self.texts] for query in queries]
