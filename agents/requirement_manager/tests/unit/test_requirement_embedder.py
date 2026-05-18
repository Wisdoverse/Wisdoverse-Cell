from agents.requirement_manager.core.embedder import RequirementEmbedder


def test_requirement_embedder_formats_requirement_for_vector_indexing():
    text = RequirementEmbedder().format_requirement_for_embedding(
        title="Offline recording",
        description="Import offline recordings.",
        category="Feature",
    )

    assert text == (
        "需求: Offline recording\n"
        "分类: Feature\n"
        "描述: Import offline recordings."
    )


def test_requirement_embedder_omits_empty_category():
    text = RequirementEmbedder().format_requirement_for_embedding(
        title="Offline recording",
        description="Import offline recordings.",
    )

    assert text == (
        "需求: Offline recording\n"
        "描述: Import offline recordings."
    )
