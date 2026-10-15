# Phase3 变更清单

基线 `evidence/phase3/baseline.json`；只列本轮触及落点。标记“共享/既有”不表示整个文件 diff 都属于本轮；baseline 未保存逐文件内容，无法从最终 git diff 精确切出此前未提交片段。未提交、推送或改子仓指针。

| 文件 | 归属 | SHA-256（生成时） |
|---|---|---|
| `.env.example` | 共享/既有 dirty 上增量 | `aaf5c7d9a87e78936f3766ead5b07deb238287881917662584460a39d6aabdbc` |
| `ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md` | 本轮新增或原 clean 文件增量 | `138309713c724f094ba097bc04da3ecfb503f04a071dfde31dac883f0b395568` |
| `ARCHITECTURE_DESIGN/README.md` | 共享/既有 dirty 上增量 | `9dc87c062b7c2c0a9e9f4cc7a34d76b29757e15c5688e23f9e2ade1bb1366b40` |
| `alembic/versions/bioopsphase3_dataset_inputs.py` | 本轮新增或原 clean 文件增量 | `d9301f568f200effe2062a89ef6c2c94066e4a452aeb5c6870aeb620f4a4c7f3` |
| `docs/adr/phase3-dataset-provenance-and-handoff.md` | 本轮新增或原 clean 文件增量 | `52461a2dddb9269d157a88877bb689df6320b6ccd3934cfa75177e9ea68ff7e1` |
| `docs/audits/cygnusx-runtime-provenance-manifest.json` | 共享/既有 dirty 上增量 | `da88936ea4171d1740f32c38a35ead11d80beda5d2fdb7e55374f8231a160840` |
| `docs/contracts/cygnusx-agent-capabilities-v1.schema.json` | 共享/既有 dirty 上增量 | `b84df1bc7ffa6c409c174088de890e01f8998d0c4b452fe7d56d628e6aadf33d` |
| `docs/contracts/cygnusx-dataset-handoff-v1.md` | 共享/既有 dirty 上增量 | `51428f831382d6e8853f4d36226da8144af30a1e03722bc33864bfadb65a9269` |
| `docs/contracts/cygnusx-dataset-handoff-v1.schema.json` | 共享/既有 dirty 上增量 | `341b0c2177d298b87a63af4c9582bef9056facf524830d52fa52217b7410a477` |
| `docs/implementation/cygnusx-phase3-dataset-ingestion-handoff-implementation.md` | 共享/既有 dirty 上增量 | `c9e06771248f5041a5447fdf25f0d2ef1bb0f8fec3eedcab24f76ec48c324d7b` |
| `flows/counts_deg.yaml` | 本轮新增或原 clean 文件增量 | `c8dc8bcac63a9b4ce5a3f0f7d8b7d71113a377643e29da2a3e84a57cfb2619f8` |
| `frontend/src/api/agentTools.ts` | 共享/既有 dirty 上增量 | `4a39338696ebce4bac148b332001b9b163f6e6c0e9c88bea9b76798a8b3ba84d` |
| `frontend/src/api/datasets.ts` | 本轮新增或原 clean 文件增量 | `35a1297a2858e00270eb6e446815e26fd960938e224d3f1cd663597993425d54` |
| `frontend/src/components/ai-chat/McpToolCallCard.vue` | 共享/既有 dirty 上增量 | `a41cbfbf1e46c12c18ba1d94e14075e7edbad49851679681f040bfa500fde68c` |
| `frontend/src/components/research/AgentToolPanel.vue` | 共享/既有 dirty 上增量 | `f1bbc43ade223be1563a510c9c63408755c370d794f126284d1924096b967b36` |
| `frontend/src/components/research/DatasetImportCard.vue` | 共享/既有 dirty 上增量 | `6472d621b5afeb0dc1984b8eda84de271f855c53c55323d3db54ac22a73a81d9` |
| `frontend/src/components/research/DatasetWorkspace.vue` | 共享/既有 dirty 上增量 | `8c21bd7b5847d1bb9a76bb412e1b57e620a2b2927b596dba6ca7f0b03169db85` |
| `frontend/src/components/research/DiscoveryProposalCard.vue` | 共享/既有 dirty 上增量 | `095546508e389ef01f06ba39b507a501f87927c7febaf73acf87fadcb0e52d6f` |
| `frontend/src/components/research/__tests__/DatasetImportCard.test.ts` | 共享/既有 dirty 上增量 | `5e61e70f8d84179bfe6f099093c8f9f2a448eb49d10b791bbe36a3c457d469c4` |
| `frontend/src/views/FilesView.vue` | 本轮新增或原 clean 文件增量 | `f50170e931571779f78183fbdd63a7cc99ee8f82d32ab7352f5054acb05accc9` |
| `frontend/src/views/FlowsView.vue` | 共享/既有 dirty 上增量 | `5f58651ec11031686247aa8420367a27bb271e60d933bd05836d3debc7d1ac86` |
| `frontend/src/views/TreasureMouseView.vue` | 共享/既有 dirty 上增量 | `be8ca4298680742168483640d547691c650393da4e1571e8b721c877295b5b5f` |
| `pipelines/CountsDEGFlow/README.md` | 本轮新增或原 clean 文件增量 | `aedd1440d6421782678f0bc1373779421bd01459b4a6873a17f33d8027dd7ec6` |
| `pipelines/CountsDEGFlow/config/config.yaml` | 本轮新增或原 clean 文件增量 | `0ec21f9726b25a15689666c68e35762555fb750cb69e378d30cd7a27a381dadb` |
| `pipelines/CountsDEGFlow/envs/deseq2.yaml` | 本轮新增或原 clean 文件增量 | `f49d9aeb130a9cf6df56732a93fbdf7cffb4429fc0cd23ad462583c3e178d4fa` |
| `pipelines/CountsDEGFlow/scripts/counts_deg.R` | 本轮新增或原 clean 文件增量 | `1d56615b7a2b2e26d1c7d786e5196bd9b792061650ef5fc17884f7ae48f334fb` |
| `pipelines/CountsDEGFlow/snakefile` | 本轮新增或原 clean 文件增量 | `2dffbf921a1800d634ca21b5982cd6c4628b6054c2bae3d451861cfacc357f4e` |
| `scripts/export_agent_tool_contracts.py` | 共享/既有 dirty 上增量 | `1f2d58c869bd42ab7d9f73a357dcb761853a2f583384aafafa3c16261cc3cc05` |
| `src/cygnusx/api/v1/datasets.py` | 本轮新增或原 clean 文件增量 | `273f6fc1dcd9d61142eb51dffccc190e59b7784d88e6a904f5e7e90edbd78042` |
| `src/cygnusx/api/v1/router.py` | 共享/既有 dirty 上增量 | `667dea17511b8180466f88bf1ece1aa0fbe2b8f10b5e8f11ebe83e377baa5976` |
| `src/cygnusx/application/schemas/agent_tools.py` | 共享/既有 dirty 上增量 | `03f687707157ddcf5c6bad0cf37159cd19d0539a126b38f1cfa29180b7cf980e` |
| `src/cygnusx/application/schemas/dataset.py` | 本轮新增或原 clean 文件增量 | `5aaa84619c1294441e62bbfbb10fb9bfbb80f8c83771916700bb0a232cb826ab` |
| `src/cygnusx/application/services/agent_service.py` | 共享/既有 dirty 上增量 | `3ad9934690714fc5fa143c445478d1178de63a7d08e1db56b3ef11c071e9b244` |
| `src/cygnusx/application/services/agent_tool_gateway.py` | 共享/既有 dirty 上增量 | `4eb7a922b2e4528a587a3e238bac598794a46d92d18faa6c59582bbe7977bd76` |
| `src/cygnusx/application/services/dataset_analysis_service.py` | 本轮新增或原 clean 文件增量 | `8bab3ea2adabcf52d8312914e72e1a06cf25e843c24c4ffd24c9eb4fa8c8fab1` |
| `src/cygnusx/application/services/dataset_handoff_service.py` | 本轮新增或原 clean 文件增量 | `1bd28c708e3193a0750d3d2535847fb79c7fb46b3f86a532961b8085963af6dc` |
| `src/cygnusx/application/services/dataset_import_service.py` | 本轮新增或原 clean 文件增量 | `843ea05c0e367cf8dbd53b1f3dfd1e624038e07fd5a1d61a5251e8cb54b86d25` |
| `src/cygnusx/application/services/dataset_service.py` | 本轮新增或原 clean 文件增量 | `7736a6fa167798c3f000c0da2ede0272363c24bbbe00efc6a2686f31f5f18ca4` |
| `src/cygnusx/application/services/flow_service.py` | 本轮新增或原 clean 文件增量 | `8e8c27d23f4fb96056fd25715ad007735a3a4da25d0ad8501398be35eb854871` |
| `src/cygnusx/application/services/geo_processed_data_service.py` | 本轮新增或原 clean 文件增量 | `20834f004c0ffacff9f9602f32b31958657188ceaf6ea388b6e3a00db07f5d85` |
| `src/cygnusx/application/services/managed_file_resolver.py` | 共享/既有 dirty 上增量 | `c349e3c62d1f71cceffc13be3a219213e4a2e6b72df3f5d38ef59656c98f0b0f` |
| `src/cygnusx/application/services/task_service.py` | 共享/既有 dirty 上增量 | `7b07093524fec95bfe5ad5ea94d17b3e4d9d783ad8c62879e4a378abe5d462b2` |
| `src/cygnusx/core/config.py` | 共享/既有 dirty 上增量 | `a533183fa5af88953a5acbbc58b8bd1ea5a33dabbd87bba6d15dd6c8754c99b2` |
| `src/cygnusx/domain/dataset/__init__.py` | 本轮新增或原 clean 文件增量 | `52f75091911db35cd16eb1b3a45844c135b53f881864219d4431f89b32d103df` |
| `src/cygnusx/domain/dataset/archives.py` | 本轮新增或原 clean 文件增量 | `890bcc9240a6c18cc28d49b429b4f1956adc92d4e3c5fd4a16c59b127cd8952a` |
| `src/cygnusx/domain/dataset/validation.py` | 本轮新增或原 clean 文件增量 | `19a531f51c2657600b80176bd067e509248154ffa33ef93784c088e8cb47c930` |
| `src/cygnusx/infrastructure/celery_app/celery.py` | 共享/既有 dirty 上增量 | `9625b68ebd61e5eeae03f2cc24ab7422c1049871c459764c872971630910890f` |
| `src/cygnusx/infrastructure/celery_app/tasks/datasets.py` | 本轮新增或原 clean 文件增量 | `60a73fb328479eff5bb7f7015cd50ff2fc035265d7cab9bf63d1d61a597204ea` |
| `src/cygnusx/infrastructure/database/models/__init__.py` | 共享/既有 dirty 上增量 | `0d8d72c62b3b95d3ae7e357c3d000e609e1bb3474113dc19771124f9d6a3b557` |
| `src/cygnusx/infrastructure/database/models/dataset.py` | 本轮新增或原 clean 文件增量 | `e7137821b856ec74d3d18e6f4d3adba24d1a3eb9310b9cc4b58ab40faccca723` |
| `src/cygnusx/infrastructure/database/repositories/dataset_repository.py` | 本轮新增或原 clean 文件增量 | `82ca965dbb6c7f9ee1112b241ad4dd20549e1857cd88e30b6c0a3d81cfae2356` |
| `src/cygnusx/infrastructure/geo/__init__.py` | 本轮新增或原 clean 文件增量 | `7106bc5d616231a2f0799aae667a7fea9a0d6b82b06da32b224013d7fa285cae` |
| `src/cygnusx/infrastructure/geo/adapter.py` | 本轮新增或原 clean 文件增量 | `ab121b60fba0eb04ea506ad7e7fb6827079db08eab1b4d0418e92947db34c9b8` |
| `src/cygnusx/infrastructure/mcp/presets.py` | 共享/既有 dirty 上增量 | `ffd3a33287a1aab3d2be5bf9b15d3fd3df843596efbd013479e049cc2d31e2d1` |
| `tests/unit/test_counts_deg_phase3.py` | 本轮新增或原 clean 文件增量 | `378718d39075bf88a1c494e5385db33d5f1b64ee126cbaa8545cfe7a8c5298e2` |
| `tests/unit/test_dataset_gateway_phase3.py` | 本轮新增或原 clean 文件增量 | `cfc165aaa7c4e89627874feadf81cf2c7e37479c98ecc2ca063233089bdb60ef` |
| `tests/unit/test_dataset_geo_validation.py` | 本轮新增或原 clean 文件增量 | `9023b97ce3086705e59b6afaa0aa537d0399c6307d7340409bed2844effdaf55` |
| `tests/unit/test_dataset_import_handoff.py` | 本轮新增或原 clean 文件增量 | `c64afe1b4a396ce55e13846d2ad594a234c638f913c6a91a55ac5db741514746` |
| `tests/unit/test_dataset_phase3.py` | 本轮新增或原 clean 文件增量 | `046801d640cbea262d98034cb494aa77ff6bafcf051f7a7197a5f1f2d0dd12f9` |
| `tests/unit/test_dataset_phase3_review.py` | 本轮新增或原 clean 文件增量 | `c2531b7b4a8cbd4e1f352fbb87506c6ecb3bb5130f0e3b76c218b7f1696711b2` |
