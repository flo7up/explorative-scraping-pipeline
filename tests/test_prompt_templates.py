from src.pipeline.prompt_templates import render_template


def test_render_template_replaces_text_and_structured_values():
    rendered = render_template(
        "Domain: {{domainDescription}}\nSchema: {{schemaJson}}",
        {
            "domainDescription": "Public real estate projects",
            "schemaJson": [{"name": "projectName", "required": True}],
        },
    )
    assert "Public real estate projects" in rendered
    assert '"projectName"' in rendered
    assert "{{" not in rendered
