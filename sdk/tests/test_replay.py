from downshift.replay import ReplayCache, extract_urls, jaccard, norm_url


def _ev(name, args, result, latency=120):
    return {"type": "tool_call", "name": name, "args": args, "result": result, "latency_ms": latency}


def test_exact_and_similar_query_matching():
    cache = ReplayCache([
        _ev("web_search", {"query": "Rosetta Stone discovery 1799", "max_results": 5}, {"r": 1}),
        _ev("web_search", {"query": "Magna Carta importance", "max_results": 5}, {"r": 2}),
    ])
    hit = cache.lookup("web_search", {"query": "rosetta stone discovery 1799", "max_results": 5})
    assert hit and hit.kind == "exact" and hit.result == {"r": 1} and hit.latency_ms == 120
    hit = cache.lookup("web_search", {"query": "discovery of the Rosetta Stone in 1799"})
    assert hit and hit.kind == "similar" and hit.result == {"r": 1}
    assert cache.lookup("web_search", {"query": "quantum error correction"}) is None


def test_url_matching_ignores_scheme_www_and_trailing_slash():
    cache = ReplayCache([_ev("read_page", {"url": "https://www.example.org/a/"}, {"text": "x"})])
    assert cache.lookup("read_page", {"url": "http://example.org/a"}).result == {"text": "x"}
    assert cache.lookup("read_page", {"url": "http://example.org/b"}) is None
    assert norm_url("HTTPS://WWW.Example.org/a/") == "example.org/a"


def test_jaccard_drops_stopwords():
    assert jaccard("what is the magna carta", "magna carta") == 1.0


def test_extract_urls_keeps_wikipedia_parentheses_and_strips_prose_punctuation():
    text = "See https://en.wikipedia.org/wiki/Trieste_(bathyscaphe). Also (https://example.org/a), and https://example.org/b?x=1#frag; done.\nSources:\nhttps://en.wikipedia.org/wiki/Swiss_Style_(design)\nhttps://en.wikipedia.org/wiki/Trieste_(bathyscaphe)"
    assert extract_urls(text) == [
        "https://en.wikipedia.org/wiki/Trieste_(bathyscaphe)",
        "https://example.org/a",
        "https://example.org/b?x=1#frag",
        "https://en.wikipedia.org/wiki/Swiss_Style_(design)",
    ]
