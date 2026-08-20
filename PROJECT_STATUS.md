# Project Status — Day 2

## Day 1

Completed baseline:

- Adult Hypertension scope
- NICE NG136 + Patient Decision Aid
- PDF extraction
- document-aware section detection
- 850/150 baseline chunking
- FastEmbed embeddings
- Chroma vector index
- Top-K retrieval
- evidence metadata
- working Day-1 UI

## Day 2

Implemented:

- 16-question evaluation set
- 500/75 vs 850/150 chunk experiments
- Top-3 / Top-5 / Top-10 evaluation
- semantic retrieval
- keyword/BM25-style retrieval
- hybrid retrieval
- optional lightweight reranking
- Precision@K + MRR
- manual relevance-labeling workflow
- evidence-first UI flow
- chat history
- reactions
- reply/follow-up
- security headers
- rate limiting
- approved-document retrieval restriction
- retrieval context binding
- prompt-injection boundary
- Day-2 documentation

## Verification completed in the build environment

```text
Python compilation: PASS
Unit/integration-style tests: 8 passed
Day-2 ingestion A (500/75): 309 chunks
Day-2 ingestion B (850/150): 212 chunks
```

The actual Chroma/FastEmbed/Groq end-to-end run should still be performed in the team's configured environment because those runtime models/dependencies may require local downloads and a valid API key.
