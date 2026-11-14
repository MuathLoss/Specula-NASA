# Docs

| File | What it is |
|---|---|
| `Specula_slides.pdf` | Our 7-slide demo: the question, the NASA data, the pipeline, the proof on 3I/ATLAS, the website, what's next |
| `Specula_project_story.md` | The project story: the idea, the five sky patches, every step we took, the problems we hit and how we fixed them, the truth tests |
| `Specula_pipeline_architecture.pdf` | The data pipeline's plan and status sheet, stage by stage |
| `Specula_frontend_data_contract.md` | The exact format of every file in `site/public/data/`: folder layout, per-patch files, 3D files, detections and scoring, the rules the site follows |
| `DATA_DICTIONARY.md` | Every folder, image layer and table column in the package the pipeline built for the detector |
| `specula_orbit.js` | Reference orbit maths for the website: position of any object from its orbital elements (elliptic and hyperbolic orbits) |
| `handoffs/detector_package/` | What the detector teammate received: README, a guide for his AI assistant (`CLAUDE.md`), `verify_and_unzip.py`, the 22 tables, and `checksums.sha256` for the image zips. The zips themselves are not public: step 6 of [`../REPRODUCE.md`](../REPRODUCE.md) rebuilds them |
| `handoffs/frontend/` | What the website teammates received: README, a guide for their AI assistant, UI ideas, and the v0.3 update note |
