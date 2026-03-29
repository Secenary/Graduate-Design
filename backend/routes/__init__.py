"""Route registration for the Flask application."""

def register_routes(app):
    from .clinical import bp as clinical_bp
    from .knowledge_graph import bp as knowledge_graph_bp
    from .proactive import bp as proactive_bp
    from .management import bp as management_bp
    from .kg_enhancement import bp as kg_enhancement_bp

    for blueprint in (
        clinical_bp,
        knowledge_graph_bp,
        proactive_bp,
        management_bp,
        kg_enhancement_bp,
    ):
        app.register_blueprint(blueprint)
