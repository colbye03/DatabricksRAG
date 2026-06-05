from app.routing import detect_intent, detect_topic, is_compare_request, product_signal_counts


def test_detect_topic_matches_keywords():
    assert detect_topic("How do I set up Unity Catalog from scratch?") == "unity_catalog_setup"
    assert detect_topic("Need an ADLS Gen2 private endpoint and private DNS for Databricks") == "adls_private_access"
    assert detect_topic("Compare Direct Lake and DirectQuery for a Power BI semantic model") == "powerbi_semantic_architecture"


def test_detect_intent_patterns():
    assert detect_intent("Prepare me for a customer call about Unity Catalog") == "meeting_prep"
    assert detect_intent("Explain this architecture in a deep explanation") == "deep_explanation"
    assert detect_intent("How do I configure this from scratch step by step?") == "deep_implementation"


def test_product_signal_counts():
    fabric_hits, databricks_hits, powerbi_hits = product_signal_counts(
        "Microsoft Fabric OneLake semantic model with Power BI and Databricks SQL warehouse"
    )
    assert fabric_hits >= 2
    assert databricks_hits >= 1
    assert powerbi_hits >= 1


def test_is_compare_request():
    assert is_compare_request("Compare Databricks versus Microsoft Fabric for analytics") is True
    assert is_compare_request("Explain Databricks Unity Catalog") is False
