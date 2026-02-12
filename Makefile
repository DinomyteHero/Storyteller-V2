.PHONY: check bootstrap test

bootstrap:
	bash scripts/bootstrap.sh

check:
	python run_app.py --check || true
	python -m pytest backend/tests/test_prompt_registry.py backend/tests/test_lore_retriever_filters.py backend/tests/test_character_voice_retriever.py backend/tests/test_style_layered_retrieval.py backend/tests/test_vector_store_factory.py tests/test_ingest_command.py backend/tests/test_health_detail.py backend/tests/test_v2_campaigns.py -q

test:
	python -m pytest backend/tests -q
