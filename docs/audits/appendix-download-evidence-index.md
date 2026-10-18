# 下载调查证据索引

基线：2026-10-16；只记录源码、脱敏本地探针与隔离测试，不包含生产凭据。

证据级别：S=当前工作树静态代码；H=宿主只读探针；I=隔离 fixture/mock 测试；R=真实 Worker 传输。本轮无 R 证据。报告 E 编号均指下表，函数行号为当前工作树位置，哈希用于检测后续漂移。

| ID | 当前路径 | SHA-256 | 关键定位 |
|---|---|---|---|
| E01 | `frontend/src/views/DownloadsView.vue` | `1c448c59fc18f43827f674f81fa952d4594d7cef9ebf59726a94b09ce932b8cb` | 98: function scfg(status: string) {<br>102: function pct(task: DownloadTask) {<br>161: function formatTime(iso: string): string {<br>166: function normalizeStatus(status: string): DownloadTask['status'] {<br>173: function mapTask(task: TaskResponse): DownloadTask {<br>211: function dedupLinks() { |
| E02 | `src/cygnusx/application/schemas/download.py` | `a764a8de75d70715f076fa1ddecb9d1caea5a24090ae705afbf271a26fa2a944` | 22: def _validate_cloud_host(provider: str, object_uri: str) -> None:<br>48: class DownloadRequest(CygnusXBaseSchema):<br>85: def validate_source_payload(self) -> "DownloadRequest": |
| E03 | `src/cygnusx/api/v1/downloads.py` | `15b182747c6c809c5fcc839d513dc17036dc7e85b32d4048d6ab7f82f6e09029` | 30: def get_download_service(db: DbSession) -> DownloadService:<br>38: def _ensure_enabled(req: DownloadRequest) -> None:<br>59: async def submit_download(<br>83: async def list_downloads(<br>96: async def get_download_progress( |
| E04 | `src/cygnusx/application/services/download_service.py` | `0bde13828fff339e1af33a3f46c2bed1ed29d3d3fed80331c1ee95f7130bf0d7` | 39: class DownloadService:<br>42: def __init__(self, db: AsyncSession, backend=None):<br>48: async def submit(self, user_id: str, req: DownloadRequest) -> TaskResponse:<br>124: async def list_downloads(self, user_id: str) -> TaskListResponse:<br>133: async def get_task_for_user(self, task_id: UUID, user_id: str) -> TaskResponse:<br>143: def _normalize_directory(directory: str / None) -> str:<br>153: def _normalize_cloud_provider(provider: str) -> str:<br>163: def _safe_path_label(value: str, fallback: str) -> str:<br>167: async def _make_work_dir(self, user_id: str, label: str, directory: str = "") -> str: |
| E05 | `src/cygnusx/infrastructure/celery_app/tasks/download.py` | `e5b83d49c0f24fb0fcb2ca35ec6169fd89dc4b1381e3ed06760a3b4085b84d89` | 32: def run_download(task_id: str) -> dict:<br>37: def _count_metadata_records(work_dir: str) -> int:<br>60: def _scan_sra_files(work_dir: str) -> tuple[dict[str, int], int]:<br>82: def _cloud_binary_path(settings, provider: str) -> str:<br>91: def _build_cloud_storage_args(<br>134: def _parse_cloud_storage_progress(message: str) -> float / None:<br>145: async def _execute_download(task_id: str) -> dict:<br>164: async def _add_and_publish_log(level: LogLevel, message: str, source: str = "") -> None:<br>179: async def _on_log(level: str, message: str, source: str = "binary") -> None:<br>190: async def _on_progress(progress: float) -> None:<br>285: async def _progress_loop() -> None:<br>338: async def _progress_poll() -> None:<br>360: async def _on_overall_progress(overall: float) -> None:<br>444: async def _execute_cloud_storage_download(<br>490: async def _on_cloud_log(level: str, message: str, source: str = "binary") -> None:<br>568: def _build_direct_link_args(<br>592: def _expand_ftp_directories(links: list[str], recursive: bool) -> list[str]:<br>608: def walk(path: str) -> None:<br>633: async def _execute_direct_link_download(<br>682: async def _on_direct_log(level: str, message: str, source: str = "aria2c") -> None:<br>740: async def _register_downloaded_files(<br>793: def _ftype(name: str) -> FileType: |
| E06 | `src/cygnusx/infrastructure/execution/binary.py` | `3d6a63d3e79701e2861986834d5dd88a337c723b827e2369526c54d41616d3cc` | 24: class BinaryExecutor(BaseExecutor):<br>27: async def execute(self, ctx: ExecutionContext) -> ExecutionResult:<br>47: async def _drain(stream: asyncio.StreamReader, sink: list[str], is_stderr: bool) -> None:<br>81: async def _emit(self, ctx: ExecutionContext, text: str, *, is_stderr: bool) -> None:<br>96: def _parse_line(text: str) -> tuple[str, str, float / None]: |
| E07 | `src/cygnusx/infrastructure/task_queue/dispatcher.py` | `1e9d1e2f89da09667f62be9ad931d11f4f56af2891b70238ae23e9b3b683c082` | 13: def _uses_rocketmq(task_name: str) -> bool:<br>22: def enqueue_task( |
| E08 | `src/cygnusx/infrastructure/celery_app/celery.py` | `9625b68ebd61e5eeae03f2cc24ab7422c1049871c459764c872971630910890f` |  |
| E09 | `tool_configs/download/download_config.yaml` | `2c9a3fbf0099ab65492123027127e1d43126fe21b8791129872166418cd4fc6f` |  |
| E10 | `src/cygnusx/tools/download/config.py` | `dfda4cbf49329c655ba2833525037531b26bd6b398b9aae8d861b45168424c6a` | 14: class DownloadFeaturesConfig(BaseModel):<br>22: class DownloadBinariesConfig(BaseModel):<br>35: def _derive_binaries(self) -> DownloadBinariesConfig:<br>49: class Aria2Config(BaseModel):<br>64: class DownloadValidationConfig(BaseModel):<br>71: class DownloadConfig(BaseModel):<br>80: class DownloadConfigManager:<br>83: def __init__(self, config_path: str / Path / None = None) -> None:<br>88: def get_config(self) -> DownloadConfig:<br>106: def reload(self) -> DownloadConfig:<br>113: def get_download_config_manager() -> DownloadConfigManager:<br>117: def get_download_config() -> DownloadConfig: |
| E11 | `src/cygnusx/application/services/agent_tool_gateway.py` | `8136e4d1f1a5dd4fc424553dfabbd8b01a9458c18b42e847e91d15a05d34a374` | 50: def require_agent_write_gate(operation: str) -> None:<br>61: def digest(payload: dict[str, Any]) -> str:<br>72: class AgentToolGateway:<br>73: def __init__(self, db: AsyncSession) -> None:<br>77: async def context(<br>147: def catalog(context: ToolInvocationContext) -> list[dict[str, Any]]:<br>167: async def invoke(<br>255: async def _plan_tool(<br>309: async def _research_tool(<br>340: async def _dataset_tool(<br>417: async def _download_proposal(<br>460: async def _proposal(<br>521: async def proposal(<br>544: async def decide(<br>576: async def task_status(self, context: ToolInvocationContext, task_id: str) -> dict[str, Any]:<br>646: async def related(self, context: ToolInvocationContext) -> list[dict[str, Any]]:<br>761: async def execute(self, context: ToolInvocationContext, proposal_id: str) -> dict[str, Any]: |
| E12 | `src/cygnusx/application/schemas/agent_tools.py` | `53eca1d27dfba1420cc7591c7a3bad14339f65d988c96ee669fd73ee94c1dc55` | 14: class ToolArgs(BaseModel):<br>18: class EmptyArgs(ToolArgs):<br>22: class WorkflowArgs(ToolArgs):<br>26: class AnalysisPrepareArgs(WorkflowArgs):<br>30: class DownloadPrepareArgs(ToolArgs):<br>35: class TaskArgs(ToolArgs):<br>39: class ExecuteArgs(ToolArgs):<br>43: class DatasetDiscoverArgs(ToolArgs):<br>47: class DatasetVersionArgs(ToolArgs):<br>52: class DatasetImportArgs(ToolArgs):<br>56: class DatasetAnalysisArgs(DatasetVersionArgs):<br>60: class AgentToolCall(ToolArgs):<br>66: class ToolProposal(BaseModel):<br>81: class TaskStatusView(BaseModel):<br>90: class GatewayResult(BaseModel):<br>96: class ToolCapability(BaseModel):<br>122: class ReportEvidenceArgs(ToolArgs):<br>126: class PlanPrepareArgs(ToolArgs):<br>130: class PlanValidateArgs(ToolArgs):<br>134: class PlanGetArgs(ToolArgs):<br>138: class ClaimArgs(TaskArgs):<br>142: class ArtifactCellArgs(ToolArgs):<br>178: def capability_catalog( |
| E13 | `src/cygnusx/api/v1/agent_tools.py` | `72af8a4d40799eec7a0b290ee6235f39309917dd330498009fcc78a8341ed27e` | 19: async def delegated_invoke(<br>34: async def capabilities(session_id: str, user: CurrentUserId, db: DbSession) -> dict[str, Any]:<br>46: async def invoke(<br>61: async def related(session_id: str, user: CurrentUserId, db: DbSession) -> list[dict[str, Any]]:<br>67: async def approve(<br>83: async def reject(<br>99: async def execute( |
| E14 | `src/cygnusx/application/services/agent_tool_delegation.py` | `7ce46b76a02411ec05e4fc8ea575c84a97bcf8e3ad642bdefd618414966bc859` | 25: def _key() -> str:<br>31: async def issue_delegation(context: ToolInvocationContext) -> str:<br>54: async def verify_delegation( |
| E15 | `src/cygnusx/application/services/dataset_import_service.py` | `afcbaddf4ad6ff94016af026f6e56d67b994b55f753c321a437e24cb4437046e` | 43: def digest(value: dict[str, Any]) -> str:<br>49: def require_dataset_read() -> None:<br>54: def require_import_write() -> None:<br>61: def metadata_adapter() -> GeoMetadataAdapter:<br>71: class DatasetImportService:<br>72: def __init__(self, db: AsyncSession, *, geo: GeoMetadataAdapter / None = None) -> None:<br>78: async def discover(self, owner: uuid.UUID, project_id: uuid.UUID / None, value: str) -> dict[str, Any]:<br>95: async def owned(<br>116: async def list_proposals(self, owner: uuid.UUID, project_id: uuid.UUID) -> list[dict[str, Any]]:<br>136: async def prepare(<br>281: async def view(<br>322: async def decide(<br>343: async def execute(<br>426: async def reconcile( |
| E16 | `src/cygnusx/infrastructure/geo/adapter.py` | `ab121b60fba0eb04ea506ad7e7fb6827079db08eab1b4d0418e92947db34c9b8` | 33: def accession(value: str) -> str:<br>40: def trusted_url(value: str, *, source_ftp: bool = False) -> str:<br>65: def parse_soft(text: str) -> dict[str, dict[str, list[str]]]:<br>78: class GeoMetadataAdapter:<br>81: def __init__(<br>101: async def _fetch(self, url: str) -> tuple[str, dict[str, Any]]:<br>148: async def resolve(self, value: str, *, refresh: bool = False) -> dict[str, Any]:<br>183: async def _geo_record(self, acc: str, result: dict[str, Any]) -> dict[str, list[str]]:<br>232: async def _geo(self, primary: str, result: dict[str, Any]) -> None:<br>269: async def _ena(self, acc: str, result: dict[str, Any]) -> None: |
| E17 | `src/cygnusx/application/services/dataset_handoff_service.py` | `1bd28c708e3193a0750d3d2535847fb79c7fb46b3f86a532961b8085963af6dc` | 37: def validation_limits() -> ValidationLimits:<br>47: class DatasetHandoffService:<br>48: def __init__(self, db: AsyncSession) -> None:<br>52: async def verify(<br>148: def _processing_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:<br>158: async def manifest(<br>332: async def provenance( |
| E18 | `src/cygnusx/application/services/dataset_service.py` | `7736a6fa167798c3f000c0da2ede0272363c24bbbe00efc6a2686f31f5f18ca4` | 26: class DatasetService:<br>27: def __init__(self, db: AsyncSession) -> None:<br>31: async def create(<br>41: async def new_version(<br>99: async def attach_asset(<br>143: async def attach_sample(<br>221: async def detail(<br>260: async def review_sample(<br>303: async def review_version(<br>328: async def review_asset_role( |
| E19 | `src/cygnusx/infrastructure/database/repositories/dataset_repository.py` | `82ca965dbb6c7f9ee1112b241ad4dd20549e1857cd88e30b6c0a3d81cfae2356` | 17: class DatasetRepository:<br>18: def __init__(self, db: AsyncSession) -> None:<br>21: async def project(<br>39: async def require_module(self, owner: uuid.UUID, module: str) -> None:<br>44: async def dataset(<br>60: async def version(<br>80: async def list(self, owner: uuid.UUID, project_id: uuid.UUID) -> list[DatasetModel]:<br>90: async def file(<br>110: async def sample(self, owner: uuid.UUID, sample_id: uuid.UUID) -> SampleModel: |
| E20 | `src/cygnusx/infrastructure/database/repositories/file_repository.py` | `c45734e6c72123756009a8999c25348df81cd81bee004f7d0d6e99f0aa3491d2` | 44: class FileRepositoryImpl(IFileRepository):<br>47: def __init__(self, session: AsyncSession):<br>50: async def get_by_id(self, user_id: UUID, file_id: UUID) -> DataFile / None:<br>58: async def get_visible(self, actor_user_id: UUID, file_id: UUID) -> DataFile / None:<br>79: async def list_by_user(<br>98: async def list_visible(<br>129: async def get_team_role(self, team_id: UUID, user_id: UUID) -> TeamRole / None:<br>143: async def save(self, file: DataFile) -> DataFile:<br>179: async def update_status(self, user_id: UUID, file_id: UUID, status: str) -> bool:<br>192: async def delete(self, user_id: UUID, file_id: UUID) -> bool:<br>201: async def delete_visible(self, actor_user_id: UUID, file_id: UUID) -> bool:<br>211: async def sum_size(self, user_id: UUID) -> int:<br>220: def _to_entity(model: FileRecordModel) -> DataFile:<br>244: class UploadSessionRepositoryImpl(IUploadSessionRepository):<br>247: def __init__(self, session: AsyncSession):<br>250: async def get_by_id(self, user_id: UUID, session_id: UUID) -> UploadSession / None:<br>258: async def find_completed(<br>287: async def save(self, session: UploadSession) -> UploadSession:<br>317: async def add_chunk(<br>339: async def update_status(self, user_id: UUID, session_id: UUID, status: str) -> bool:<br>352: async def delete(self, user_id: UUID, session_id: UUID) -> bool:<br>362: def _to_entity(model: UploadSessionModel) -> UploadSession:<br>382: class SampleRepositoryImpl(ISampleRepository):<br>385: def __init__(self, session: AsyncSession):<br>388: async def get_by_id(self, user_id: UUID, sample_id: UUID) -> Sample / None:<br>396: async def list_by_user(self, user_id: UUID) -> list[Sample]:<br>405: async def count_by_user(self, user_id: UUID) -> int:<br>410: async def save(self, sample: Sample) -> Sample:<br>436: async def delete(self, user_id: UUID, sample_id: UUID) -> bool:<br>446: def _to_entity(model: SampleModel) -> Sample:<br>464: class DirectoryRepositoryImpl(IDirectoryRepository):<br>467: def __init__(self, session: AsyncSession):<br>470: async def list_by_user(self, user_id: UUID) -> list[Directory]:<br>479: async def get_by_path(self, user_id: UUID, path: str) -> Directory / None:<br>487: async def save(self, directory: Directory) -> Directory:<br>509: async def delete(self, user_id: UUID, path: str) -> bool: |
| E21 | `src/cygnusx/domain/file/entities.py` | `26fee890e8cb3a0ed48c7ce3c7860e4430daa95fc2e51e83f53917c91d846156` | 12: class DataFile(BaseModel):<br>32: class Directory(BaseModel):<br>45: class Sample(BaseModel):<br>60: class UploadSession(BaseModel): |
| E22 | `src/cygnusx/infrastructure/database/models/file.py` | `21a1cce65ba40badc5a8e003729af81c43e67f6ee4fde412550307699a93ce74` | 28: class FileRecordModel(Base, TimestampMixin):<br>78: class UploadSessionModel(Base, TimestampMixin):<br>100: class SampleModel(Base, TimestampMixin):<br>118: class DirectoryModel(Base, TimestampMixin): |
| E23 | `src/cygnusx/application/services/tool_confirmation_service.py` | `802694e956a40f742b5212ff513d3c7d91c5fed653a3529b587b7d2fd41262be` | 66: class ConfirmationError(Exception):<br>69: def __init__(self, code: str, message: str):<br>76: class ConfirmationRecord:<br>97: def to_json(self) -> str:<br>105: def from_json(cls, raw: str) -> ConfirmationRecord:<br>131: class ApprovalResult:<br>140: class _MemoryStore:<br>145: def __init__(self) -> None:<br>149: async def save(self, record: ConfirmationRecord) -> None:<br>154: async def get(self, confirmation_id: str) -> ConfirmationRecord / None:<br>165: async def transition(<br>181: def _purge_locked(self) -> None:<br>192: class _RedisStore:<br>198: def __init__(self, client: Any) -> None:<br>202: async def save(self, record: ConfirmationRecord) -> None:<br>209: async def get(self, confirmation_id: str) -> ConfirmationRecord / None:<br>222: async def transition(<br>246: class ToolConfirmationService:<br>251: def __init__(self, store: _MemoryStore / _RedisStore / None = None) -> None:<br>255: async def _get_store(self) -> _MemoryStore / _RedisStore:<br>275: async def create(<br>305: async def create_for_tool(<br>338: async def approve_by_human(<br>364: async def approve(<br>462: async def consume_tool_confirmation(<br>513: async def reject(<br>533: async def get_status(self, user_id: str, confirmation_id: str) -> ConfirmationRecord / None:<br>542: async def _require_owned(self, user_id: str, confirmation_id: str) -> ConfirmationRecord:<br>549: async def _transition(<br>556: def _hash(payload: dict[str, Any]) -> str:<br>565: def get_tool_confirmation_service() -> ToolConfirmationService: |
| E24 | `src/cygnusx/api/deps.py` | `00414ecdb3a095e4b3d38b9b8dec281048a1b9cd643259573c28b7372ef89db0` | 23: async def get_db() -> AsyncIterator[AsyncSession]:<br>48: def require_human_or_confirmation(request: Request, confirmation_id: str / None) -> None:<br>64: async def get_current_user_id(<br>81: async def _authenticate_api_key(api_key: str) -> str:<br>92: async def _authenticate_jwt(token: str) -> str:<br>118: async def get_current_jwt_user_id(<br>130: async def require_admin_totp(<br>160: async def require_admin(<br>180: async def get_active_user_from_token_payload(payload: dict[str, Any]) -> UserModel / None: |
| E25 | `src/cygnusx/application/services/tool_bridge_service.py` | `8fcbe21ff6bd10c46ee731959dde0670cfda3ccb1b719e36eae6765633e34324` | 30: class ToolBridgeService:<br>39: def __init__(<br>48: async def execute(<br>185: def _validate_and_sanitize(<br>241: def _coerce_number(key: str, value: Any, expected_type: str) -> int / float:<br>267: def _coerce_boolean(key: str, value: Any) -> bool:<br>280: def _coerce_json(key: str, value: Any, expected_type: str) -> list / dict:<br>296: async def _resolve_upload_refs(<br>331: async def _read_chat_upload(self, user_id: str, file_id: str) -> str / None:<br>354: async def _dispatch(<br>377: async def _execute_analysis_flow(<br>417: def _package_analysis_flow_result(self, raw: dict[str, Any]) -> dict[str, Any]:<br>486: async def _submit_async_arq(<br>527: async def _run_service_sync(<br>570: async def _run_shim(<br>587: def _open_page_payload(self, schema: ToolSchema, args: dict[str, Any]) -> dict[str, Any]:<br>596: def _package(self, schema: ToolSchema, raw: dict[str, Any]) -> dict[str, Any]:<br>640: def _pick(data: dict[str, Any], fields: list[str]) -> dict[str, Any]:<br>649: def _safe_preview(args: dict[str, Any]) -> dict[str, Any]:<br>660: def _attach_ignored_params(envelope: dict[str, Any], ignored_params: list[str]) -> None:<br>666: def _error(<br>693: def get_tool_bridge_service() -> ToolBridgeService: |
| E26 | `src/cygnusx/infrastructure/mcp/presets.py` | `3fda2e7796da4021e8265f9b3bd13b3120d2191347bb0fe3bc3273298f04c242` | 35: async def _cygnusx_tools_handler(<br>82: def _load_workspace_files_prompt() -> str:<br>95: async def _platform_list_tasks(<br>114: async def _platform_get_task(<br>133: async def _platform_sandbox_execute(<br>147: async def execute(db: Any) -> dict[str, Any]:<br>179: async def _platform_list_flows(arguments: dict[str, Any], **_kw: Any) -> dict[str, Any]:<br>193: async def _platform_get_current_time(<br>219: async def _platform_list_agent_skills(<br>239: async def query(db: Any) -> dict[str, Any]:<br>285: async def _platform_get_user_info(<br>301: async def fetch(db: Any) -> dict[str, Any]:<br>356: def _fmt(num: float) -> str:<br>376: async def _platform_admin_health_check(<br>399: async def inspect(db: Any) -> dict[str, Any]:<br>488: async def _platform_read_file(<br>552: def _is_text_file(name: str) -> bool:<br>557: def _human_size(size: int) -> str:<br>565: async def _extract_workspace_pdf_text(<br>601: async def _resolve_workspace_file(<br>695: async def _workspace_list_files(<br>714: async def _list_workspace_files(<br>774: async def _search_workspace_files(<br>826: async def _find_session_uploads(<br>922: async def _workspace_get_file_info(<br>945: async def _workspace_read_file(<br>1035: async def _platform_submit_download(<br>1153: async def _platform_list_downloads(<br>1179: async def _platform_get_download_progress(<br>1242: async def _platform_europe_pmc_search(<br>1284: async def _platform_arxiv_search(<br>1310: async def _platform_ability_catalog_query(<br>1332: def bindings(config: dict[str, Any]) -> dict[str, Any]:<br>1400: async def _platform_room_state_query(<br>1424: async def query(db: Any) -> dict[str, Any]:<br>1463: async def _seqout_handler( |
| E27 | `mcp-server/tools/downloads.py` | `a2dbd06e99b7422f96650805cb41e4fcf31dd9d0f632ac8e52179d021ef50cdd` | 7: def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:<br>10: async def cygnusx_submit_download(<br>155: async def cygnusx_list_downloads() -> dict:<br>183: async def cygnusx_get_download_progress(task_id: str) -> dict: |
| E28 | `deploy/docker/docker-compose.worker.yml` | `1bd3afbbf164bb850b3d4bb7f6c68a441b9e08966b54ae24c17c3c3df07139fd` |  |
| E29 | `deploy/docker/Dockerfile.worker` | `2be1716a5e7ec1daad78ee32007fbb20632b891bed06429ad2473708ab8f6548` |  |
| E30 | `pipelines/EBIDownload/crates/ebidownload-cli/src/main.rs` | `84e5aab874b13f2766dc0743ef6a92ad422d7dd2cc61b7481448b605768593e3` | 793: pub fn create_script(output_path: &Path, fastq_id: &str, command: &str) -> Result<PathBuf> { |
| E31 | `pipelines/EBIDownload/crates/ebidownload-core/src/lib.rs` | `7064da445f3fe185e9da0daaee68b26a2b5767d4328738ee395d98dceca123b0` | 182: pub fn load_config(yaml_path: &Path) -> Result<Config> {<br>194: pub async fn fetch_ena_data(accession: &str) -> Result<Vec<EnaRecord>> {<br>221: pub fn read_tsv_data(tsv_path: &Path) -> Result<Vec<EnaRecord>> {<br>244: pub fn new(options: &DownloadOptions) -> Result<Self> {<br>273: pub fn should_include(&self, record: &EnaRecord) -> bool {<br>282: pub fn process_records(<br>349: pub fn compress_fastq_files(<br>432: pub fn generate_md5sum_file(<br>459: pub fn validate_config(config: &Config, method: DownloadMethod) -> Result<()> { |
| E32 | `pipelines/EBIDownload/crates/ebidownload-core/src/ftp.rs` | `6fc2f6b15c9d670400536122079132a578c938ae036e08e0ee7d122c16a17121` | 19: pub async fn process_downloads( |
| E33 | `Protocol/FlowFrame/FlowAgent/src/tools/platform.ts` | `bf75e31f8b009372e6d299eec1fcefe9250a76e3a2a21216f2c45f1d22050d68` |  |
| E34 | `src/cygnusx/infrastructure/mas/ebi.py` | `3e4191e6cf562bbdaf05d8ed11b69e4460e0c09525d5c51b0d4ce4cf704363e2` | 11: class EBIDownloadError(ValueError):<br>19: def build_ebi_download_command(<br>57: def write_download_manifest(staging_directory: Path, manifest_path: Path, accession: str) -> dict[str, object]:<br>76: def _sha256(path: Path) -> str: |
| E35 | `src/cygnusx/application/services/task_service.py` | `1004632d5c36e1badcf3e93c35cbbafdc0018690e893c69d769e83e9c4b92922` | 41: class TaskService:<br>44: def __init__(<br>56: async def submit(self, user_id: str, req: TaskSubmitRequest) -> TaskResponse:<br>221: async def get_task(self, task_id: UUID, user_id: str) -> TaskResponse:<br>233: async def list_tasks(<br>258: async def _attach_user_display_info(self, items: list[TaskResponse]) -> None:<br>274: async def cancel_task(self, task_id: UUID, user_id: str) -> TaskResponse:<br>301: async def delete_task(self, task_id: UUID, user_id: str) -> None:<br>321: async def get_task_dag(self, task_id: UUID, user_id: str) -> dict[str, Any]:<br>345: def _write_monitor_config(<br>381: def _make_work_dir(self, flow_id: str, project_name: str, user_id: str) -> str: |
| E36 | `src/cygnusx/domain/task/value_objects.py` | `d4bbff9b0a15925df0467db169d339c11b71e8bebf1a1c3596f37fff9292aa09` | 6: class TaskStatus(str, Enum):<br>17: class ExecutionMode(str, Enum):<br>24: class LogLevel(str, Enum): |
| E37 | `src/cygnusx/domain/dataset/archives.py` | `890bcc9240a6c18cc28d49b429b4f1956adc92d4e3c5fd4a16c59b127cd8952a` | 20: class ArchiveLimits:<br>27: def expand_archive(<br>39: def write_member(member_name: str, content: ByteReader, declared_size: int / None) -> None: |
| E38 | `src/cygnusx/domain/dataset/validation.py` | `19a531f51c2657600b80176bd067e509248154ffa33ef93784c088e8cb47c930` | 21: class ByteReader(Protocol):<br>22: def read(self, size: int = -1) -> bytes: ...<br>23: def readline(self, size: int = -1) -> bytes: ...<br>24: def seek(self, offset: int, whence: int = 0) -> int: ...<br>28: class ValidationLimits:<br>36: def open_owned_file(path: Path, owner_root: Path) -> BinaryIO:<br>69: def checksum(stream: ByteReader, limits: ValidationLimits) -> tuple[str, int]:<br>81: def _lines(stream: ByteReader, limits: ValidationLimits) -> Iterator[str]:<br>96: def inspect_matrix(<br>221: def inspect_fastq(stream: ByteReader, *, limits: ValidationLimits / None = None) -> dict[str, Any]:<br>257: def inspect_content(<br>301: def inspect_sample_metadata( |
| E39 | `src/cygnusx/api/v1/datasets.py` | `dedcdda405e6a04e4d30b6e881cffd7fe6e354cba7e91a4a9fe3cf97a0d6dc7d` | 32: async def dataset_read_dependency() -> None:<br>43: async def list_datasets(<br>60: async def create_dataset(<br>69: async def dataset_detail(<br>76: async def new_version(<br>90: async def assets(<br>126: async def attach_asset(<br>145: async def samples(<br>177: async def attach_sample(<br>192: async def verify(<br>199: async def handoff(<br>206: async def freeze(<br>215: async def provenance(<br>224: async def discover(<br>231: async def prepare_import(<br>238: async def import_proposal(<br>245: async def decide_import(<br>264: async def analysis_prepare(<br>280: async def review_sample(<br>295: async def compatible_workflows(<br>306: async def decide_analysis(<br>338: async def expand_asset(<br>354: async def import_proposals(<br>361: async def analysis_proposal(<br>377: async def review_version(<br>391: async def review_asset_role( |
| E40 | `src/cygnusx/api/v1/files.py` | `f0b2a7efeeaab152da3f63295baf7c7a593594418268f68edf725ed87ad4eabd` | 148: def _validate_chat_upload_filename(filename: str / None) -> None:<br>167: def get_file_service(db: DbSession) -> FileService:<br>176: async def list_files(<br>204: async def search_files(<br>227: async def list_workspace_files(<br>249: async def file_tree(<br>258: async def get_quota(<br>267: async def storage_info() -> dict[str, object]:<br>283: async def preview_file(<br>296: async def sync_files(<br>313: async def presigned_download(<br>334: async def presigned_upload(<br>362: async def presigned_upload_complete(<br>379: async def list_directories(<br>388: async def create_directory(<br>398: async def delete_directory(<br>409: async def list_files_for_picker(<br>422: async def move_file(<br>433: async def init_upload(<br>446: async def upload_chunk(<br>460: async def merge_upload(<br>470: async def cancel_upload(<br>481: async def upload_chat_file(<br>530: async def download_chat_file(<br>558: async def download_file(<br>569: async def delete_file(<br>581: async def list_samples(<br>589: async def create_sample( |
| E41 | `src/cygnusx/core/config.py` | `5da23063e07fd316f4a291fb407793bc496c82f3997bfbc72c0d3afbc3607f82` | 11: class ContextCompactionSettings(BaseSettings):<br>29: class Settings(BaseSettings):<br>641: def derive_mas_workspace_root(cls, v: str, info: Any) -> str:<br>650: def derive_sandbox_pool_host_dir(cls, v: str, info: Any) -> str:<br>659: def validate_manager_agent_id(cls, v: Any) -> str:<br>668: def assemble_database_url(cls, v: str, info: Any) -> str:<br>680: def assemble_celery_broker(cls, v: str, info: Any) -> str:<br>694: def assemble_celery_backend(cls, v: str, info: Any) -> str:<br>706: def derive_storage_relative_defaults(self) -> "Settings":<br>745: def validate_production_secrets(self) -> "Settings":<br>781: def _is_placeholder(value: str) -> bool:<br>790: def redis_url(self) -> str:<br>795: def is_production(self) -> bool:<br>800: def get_settings() -> Settings:<br>805: def reload_settings() -> Settings: |
| E42 | `src/cygnusx/application/services/research_treasure_service.py` | `1756625ed25810d2bec97b3d4132b9183b0a113696368ca9816ad0f0a9dec854` | 41: def _source_link(accession: str / None) -> str / None:<br>53: def card_to_proposal(<br>89: def merge_discovery_cards(<br>107: class TreasureAgentAdapter:<br>110: def __init__(self, settings: Settings / None = None) -> None:<br>113: async def literature(self, *, kind: str, identifier: str, principal_id: str) -> dict[str, Any]:<br>134: async def stream(<br>193: class ResearchTreasureService:<br>194: def __init__(self, db: AsyncSession, *, adapter: TreasureAgentAdapter / None = None) -> None:<br>201: def ensure_enabled() -> None:<br>205: async def _current_user(self, user_id: str) -> UserModel:<br>212: async def capabilities(self, user_id: str) -> ResearchAgentCapabilities:<br>238: async def ensure_access(self, user_id: str) -> None:<br>244: async def _owned_project(self, user_id: str, project_id: str / None) -> None:<br>260: async def _provider(self, model_id: uuid.UUID / None) -> AIProviderConfigModel:<br>275: async def create_session(<br>303: async def list_sessions(self, user_id: str, project_id: str / None) -> list[Any]:<br>318: async def _owned_session(self, user_id: str, session_id: str) -> ChatSessionModel:<br>332: async def messages(self, user_id: str, session_id: str) -> list[Any]:<br>337: async def update_session(<br>348: async def literature(<br>356: async def check_stream_access(<br>362: async def cancel(self, user_id: str, session_id: str) -> bool:<br>370: async def stream_message( |
| E43 | `src/cygnusx/application/services/agent_service.py` | `bba617e6dd5260f9f091235d7fdfbfd638d73d501ae9872401d3df8f0e66d6f5` | 87: def _mcp_mount_allowed_for_agent(server: MCPServer) -> bool:<br>154: def _bounded_persona_text(value: Any) -> str:<br>159: def render_persona_system_prompt(features: dict[str, Any] / None) -> str:<br>199: def _generate_agent_id(name: str) -> str:<br>207: class AgentContext:<br>222: class AgentService:<br>225: def __init__(self, db: AsyncSession) -> None:<br>231: async def ensure_builtin_agents(self) -> None:<br>388: async def _ensure_configured_marketplace_skills(self, skill_ids: set[str]) -> None:<br>420: async def list_agents(self, active_only: bool = False) -> list[AgentTemplateDTO]:<br>430: async def list_user_selectable_mcps(self) -> list[UserSelectableMCPDTO]:<br>448: async def get_agent(self, agent_id: str) -> AgentTemplateModel / None:<br>454: async def get_agent_dto(self, agent_id: str) -> AgentTemplateDTO:<br>461: async def get_user_capabilities(<br>487: async def update_user_capabilities(<br>514: async def reset_user_capabilities(self, user_id: str, agent_id: str) -> None:<br>521: async def _get_user_capability(<br>532: async def _validate_user_capability_assets(<br>573: def _dedupe_ids(items: list[str]) -> list[str]:<br>577: def _effective_user_features(<br>590: def _validate_user_feature_selection(<br>605: async def update_agent(self, agent_id: str, req: UpdateAgentRequest) -> AgentTemplateDTO:<br>633: async def create_agent(self, req: CreateAgentRequest) -> AgentTemplateDTO:<br>662: def _normalize_json_lists(data: dict[str, Any]) -> None:<br>668: async def _validate_model_id(self, data: dict[str, Any]) -> None:<br>682: async def _sync_model_labels(self, data: dict[str, Any]) -> None:<br>704: async def _reconcile_model_bindings(self) -> None:<br>751: async def delete_agent(self, agent_id: str) -> bool:<br>769: async def toggle_agent(self, agent_id: str) -> AgentTemplateDTO:<br>790: async def _find_default_successor(<br>805: async def set_default_agent(self, agent_id: str) -> None:<br>813: async def _clear_other_defaults(self) -> None:<br>822: async def assemble_context(<br>1091: def _append_persona_prompt(system_prompt: str, agent: AgentTemplateModel) -> str:<br>1108: def _append_communication_contract(system_prompt: str, agent: AgentTemplateModel) -> str:<br>1120: async def _agentteams_chat_entry_enabled(self) -> bool: |
| E44 | `src/cygnusx/tools/schema_loader.py` | `e6211fab0cb1384eb0274e24d402611dedd825ef1caf5a20fbc39bd780b93bba` | 21: class ToolAnnotation(BaseModel):<br>32: class ToolSchema(BaseModel):<br>59: def resolve_runtime_image(self) -> str / None:<br>72: def resolve_mas_execution_policy(self) -> object / None:<br>83: class ToolsSchemaRegistry(BaseModel):<br>92: class ToolsSchemaLoader:<br>95: def __init__(self, config_path: str / Path / None = None) -> None:<br>104: def _load_yaml(self) -> dict[str, Any]:<br>116: def _rebuild_index(self) -> None:<br>129: def reload(self) -> ToolsSchemaRegistry:<br>135: def get_config(self) -> ToolsSchemaRegistry:<br>172: def list_tools(self) -> list[ToolSchema]:<br>176: def _load_flow_tools(self) -> list[ToolSchema]:<br>260: def get_tool(self, name: str) -> ToolSchema / None:<br>265: def to_openai_tools(self, category: str / None = None) -> list[dict[str, Any]]:<br>283: def search_tools(self, query: str, limit: int = 8) -> list[ToolSchema]:<br>303: def select_tools(<br>324: def _tokenize(value: str) -> list[str]:<br>337: def build_system_hint(self, allowed_names: set[str] / None = None) -> str:<br>348: def toolbox_catalog(self, query: str, limit: int = 20) -> list[dict[str, str]]:<br>363: def get_tools_schema_loader() -> ToolsSchemaLoader: |
| E45 | `src/cygnusx/application/services/upload_service.py` | `1985207588df61a89a452418adb5442b7be3c6e9e1e0ea86066da6281f711efd` | 51: def _normalize_directory(directory: str / None) -> str:<br>59: class UploadService:<br>62: def __init__(self, session: AsyncSession, backend=None):<br>71: async def _inbox_subdir(self, user_id: UUID, directory: str) -> Path:<br>83: async def _resolve_completed_file_id(<br>105: async def init_upload(<br>162: async def save_chunk(<br>199: async def merge_upload(<br>247: async def iter_chunks() -> AsyncIterator[bytes]:<br>304: async def cancel_upload(self, user_id: UUID, upload_id: UUID) -> bool: |

## Git 基线（调查起点已有脏文件）

主仓 `feat/research-agent-phase5` / `51011118535f782f5282f638b4a54649c79bf6d6`。以下状态在新增调查文档前采集；不意味着这些修改由本轮产生。

```text
M .env.example
 M .gitignore
 M ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md
 M ARCHITECTURE_DESIGN/CygnusX_flow_architecture.md
 M ARCHITECTURE_DESIGN/CygnusX_frontend.md
 M ARCHITECTURE_DESIGN/CygnusX_mcp_architecture.md
 M ARCHITECTURE_DESIGN/README.md
 m Protocol/FlowFrame
 M deploy/docker/Dockerfile.frontend
 M deploy/docker/nginx/frontend.conf
 M deploy/docker/nginx/nginx.conf
 M deploy/docker/nginx/nginx.prod.conf
 D docs/info/26.10.11/2026-10-12_15.20.10.png
 D docs/info/26.10.11/CygnusX_Design_System_v1.md
 D docs/info/26.10.11/CygnusX_Frontend_Issues_Backlog.md
 D docs/info/26.10.11/CygnusX_Frontend_Optimization_Implementation_Report.md
 D docs/info/26.10.11/CygnusX_UI_Regression_Checklist.md
 D docs/info/26.10.11/CygnusX__v1.0_Codex.md
 D docs/info/26.10.11/CygnusX_frontend_W00_report.md
 D docs/info/26.10.11/CygnusX_frontend_W01_report.md
 D docs/info/26.10.11/CygnusX_frontend_W02_report.md
 D docs/info/26.10.11/CygnusX_frontend_W03_report.md
 D docs/info/26.10.11/CygnusX_frontend_W04_report.md
 D docs/info/26.10.11/CygnusX_frontend_W05_report.md
 D docs/info/26.10.11/CygnusX_frontend_W06_report.md
 D docs/info/26.10.11/CygnusX_frontend_W07_report.md
 D docs/info/26.10.11/CygnusX_frontend_W08_report.md
 D docs/info/26.10.11/CygnusX_frontend_W09_report.md
 D docs/info/26.10.11/CygnusX_frontend_W10_report.md
 D docs/info/26.10.11/CygnusX_frontend_W11_report.md
 D docs/info/26.10.11/CygnusX_frontend_W12_report.md
 D docs/info/26.10.11/CygnusX_frontend_W13_report.md
 D docs/info/26.10.11/CygnusX_frontend_W14_report.md
 D docs/info/26.10.11/CygnusX_frontend_W15_report.md
 D docs/info/26.10.11/CygnusX_frontend_W16_report.md
 D docs/info/26.10.11/CygnusX_frontend_W17_report.md
 D "docs/info/26.10.11/CygnusX_\345\211\215\347\253\257\345\205\250\345\271\263\345\217\260\346\234\200\347\273\210\344\274\230\345\214\226\345\256\236\346\226\275\350\247\204\350\214\203_v2.0_Codex.md"
 D docs/info/26.10.12/2026-10-13_01.50.30.png
 D docs/info/26.10.12/2026-10-13_01.51.21.png
 D docs/info/26.10.12/2026-10-13_14.09.13.png
 D docs/info/26.10.12/2026-10-13_20.36.02.png
 D docs/info/26.10.12/2026-10-13_21.44.25.png
 D "docs/info/26.10.12/2026-10-13\342\200\224\342\200\22401.49.41.png"
 D docs/info/26.10.12/2026-10-1_14.26.17.png
 D docs/info/26.10.12/CygnusX_Phase1.md
 D docs/info/26.10.12/CygnusX_Phase3__2026-10-15.md
 D "docs/info/26.10.12/CygnusX_Phase4_\347\247\221\347\240\224\350\257\201\346\215\256\351\223\276\344\270\216\345\217\257\345\244\215\347\216\260\346\212\245\345\221\212\344\272\244\344\273\230.md"
 D "docs/info/26.10.12/CygnusX\345\205\263\344\272\216\351\241\265\351\235\242\345\270\203\345\261\200\344\274\230\345\214\226\345\256\236\346\226\275\350\256\241\345\210\222.md"
 D "docs/info/26.10.12/\345\205\261\344\272\253+Agent+\345\267\245\345\205\267\345\261\202\344\270\216\344\273\273\345\212\241\347\274\226\346\216\222.md"
 D "docs/info/26.10.12/\345\217\257\345\244\215\347\216\260\346\212\245\345\221\212\345\212\237\350\203\275\350\256\276\350\256\241\346\241\206\346\236\266.md"
 D docs/info/26.10.2/2026-10-03_13.45.25.png
 D docs/info/26.10.2/2026-10-03_15.09.40.png
 D "docs/info/26.10.2/\346\210\252\345\261\2172026-10-02 23.55.27.png"
 D "docs/info/26.10.2/\346\210\252\345\261\2172026-10-02 23.55.39.png"
 D "docs/info/26.10.2/\346\210\252\345\261\2172026-10-02 23.55.51.png"
 D "docs/info/26.10.2/\346\210\252\345\261\2172026-10-02 23.56.01.png"
 D "docs/info/26.10.2/\346\210\252\345\261\2172026-10-03 11.13.14.png"
 D docs/info/26.10.3/2026-10-03_20.30.21.png
 D docs/info/26.10.3/2026-10-03_22.45.42.png
 D docs/info/26.10.3/agent-sandbox-audit-prompt.md
 D docs/info/26.10.3/agent-sandbox-remediation-plan.md
 D "docs/info/26.10.3/\344\270\252\344\272\272\347\251\272\351\227\264\347\233\256\345\275\225\346\262\273\347\220\206-\350\241\245\345\205\205\350\260\203\346\237\245\346\212\245\345\221\212.md"
 D "docs/info/26.10.3/\344\270\252\344\272\272\347\251\272\351\227\264\347\233\256\345\275\225\346\262\273\347\220\206-\350\241\245\345\205\205\350\260\203\346\237\245\346\217\220\347\244\272\350\257\215.md"
 D "docs/info/26.10.3/\345\255\230\345\202\250\345\261\202\344\274\230\345\214\226-Phase0\351\242\204\346\243\200\346\212\245\345\221\212.md"
 D "docs/info/26.10.3/\345\255\230\345\202\250\345\261\202\344\274\230\345\214\226\345\256\236\346\226\275\346\217\220\347\244\272\350\257\215.md"
 D "docs/info/26.10.3/\345\255\230\345\202\250\345\261\202\344\274\230\345\214\226\345\256\236\346\226\275\346\226\271\346\241\210.md"
 D "docs/info/26.10.3/\346\225\260\346\215\256\347\256\241\347\220\206\345\211\215\347\253\257\344\274\230\345\214\226\346\226\271\346\241\210.md"
 D "docs/info/26.10.3/\346\225\260\346\215\256\347\256\241\347\220\206\345\211\215\347\253\257\347\216\260\347\212\266\350\260\203\346\237\245.md"
 D "docs/info/26.10.3/\346\225\260\346\215\256\347\256\241\347\220\206\345\211\215\347\253\257\350\241\245\345\205\205\350\260\203\346\237\245\346\212\245\345\221\212.md"
 D "docs/info/26.10.3/\346\225\260\346\215\256\347\256\241\347\220\206\345\211\215\347\253\257\350\241\245\345\205\205\350\260\203\346\237\245\346\217\220\347\244\272\350\257\215.md"
 D docs/info/26.10.9/CygnusX_model_routing_current_state.md
 D docs/info/26.10.9/CygnusX_routing_implementation_merged.md
 D "docs/info/26.8.19/L4\345\215\217\344\275\234\345\256\244\344\270\216\346\226\207\344\273\266\347\263\273\347\273\237\350\236\215\345\220\210\344\274\230\345\214\226\345\256\236\346\226\275\346\211\213\345\206\214.md"
 D "docs/info/26.8.19/L4\346\204\277\346\231\257\350\220\275\345\234\260\345\256\236\346\226\275\350\256\241\345\210\222.md"
 D "docs/info/26.8.19/\345\215\217\344\275\234\345\256\244\345\271\263\345\217\260\345\234\260\345\237\272\344\274\230\345\214\226\345\256\236\346\226\275\346\211\213\345\206\214.md"
 D "docs/info/26.8.19/\345\215\217\344\275\234\345\256\244\345\271\263\345\217\260\345\274\202\345\270\270\346\216\222\346\237\245\344\273\243\347\240\201\345\256\241\346\237\245\346\212\245\345\221\212_2026-08-19.md"
 D "docs/info/26.8.20/Manager\344\272\272\346\240\274\345\210\206\345\261\202\345\256\236\346\226\275\346\211\213\345\206\214-\351\200\232\347\224\250\345\212\251\346\211\213\344\270\216\351\203\250\351\227\250\347\273\217\347\220\206\345\205\261\345\255\230.md"
 D "docs/info/26.8.20/image copy 10.png"
 D "docs/info/26.8.20/image copy 11.png"
 D "docs/info/26.8.20/image copy 12.png"
 D "docs/info/26.8.20/image copy 13.png"
 D "docs/info/26.8.20/image copy 14.png"
 D "docs/info/26.8.20/image copy 15.png"
 D "docs/info/26.8.20/image copy 16.png"
 D "docs/info/26.8.20/image copy 17.png"
 D "docs/info/26.8.20/image copy 18.png"
 D "docs/info/26.8.20/image copy 19.png"
 D "docs/info/26.8.20/image copy 2.png"
 D "docs/info/26.8.20/image copy 20.png"
 D "docs/info/26.8.20/image copy 3.png"
 D "docs/info/26.8.20/image copy 4.png"
 D "docs/info/26.8.20/image copy 5.png"
 D "docs/info/26.8.20/image copy 6.png"
 D "docs/info/26.8.20/image copy 7.png"
 D "docs/info/26.8.20/image copy 8.png"
 D "docs/info/26.8.20/image copy 9.png"
 D "docs/info/26.8.20/image copy.png"
 D docs/info/26.8.20/image.png
 D "docs/info/26.8.20/\345\215\217\344\275\234\345\256\244Manager\345\217\215\345\244\215\350\277\275\351\227\256\346\225\260\346\215\256\346\235\245\346\272\220-\344\273\243\347\240\201\350\260\203\347\240\224\346\212\245\345\221\212_2026-08-20.md"
 D "docs/info/26.8.20/\345\215\217\344\275\234\345\256\244Manager\345\217\215\345\244\215\350\277\275\351\227\256\346\225\260\346\215\256\346\235\245\346\272\220-\344\273\243\347\240\201\350\260\203\347\240\224\346\217\220\347\244\272\350\257\215.md"
 D "docs/info/26.8.20/\345\215\217\344\275\234\345\256\244Manager\345\217\215\345\244\215\350\277\275\351\227\256\346\225\260\346\215\256\346\235\245\346\272\220-\350\260\203\347\240\224\346\240\270\345\257\271\344\270\216\344\277\256\345\244\215\345\256\236\346\226\275\350\256\241\345\210\222.md"
 D "docs/info/26.8.21/CygnusXBioOps_\345\210\235\350\265\233_v1.pdf"
 D "docs/info/26.8.21/F9_Manager\347\273\204\351\230\237\350\264\250\351\207\217\350\257\204\346\265\213\346\212\245\345\221\212.md"
 D "docs/info/26.8.21/W0_\347\246\201\344\273\244\346\224\271\345\206\231\345\257\271\347\205\247\350\241\250.md"
 D "docs/info/26.8.21/W0_\351\255\224\346\225\260\350\257\201\346\215\256\346\263\250\351\207\212\346\270\205\345\215\225.md"
 D "docs/info/26.8.21/image copy 2.png"
 D "docs/info/26.8.21/image copy.png"
 D docs/info/26.8.21/image.png
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244L4\345\256\241\346\237\245\344\277\256\345\244\215\344\270\216\344\274\230\345\214\226\345\256\236\346\226\275\346\211\213\345\206\214.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244L4\346\204\277\346\231\257\347\254\246\345\220\210\345\272\246\345\256\241\346\237\245\346\212\245\345\221\212-2026-08-21.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244L4\346\204\277\346\231\257\347\254\246\345\220\210\345\272\246\345\256\241\346\237\245\346\217\220\347\244\272\350\257\215.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244N1-N6\345\234\260\345\237\272\346\240\270\345\256\236\346\212\245\345\221\212-2026-08-21.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\345\217\214\347\272\277\346\226\275\345\267\245\344\273\273\345\212\241\344\271\246-\344\270\211\344\273\266\345\245\227\345\256\236\347\216\260\344\270\216\345\234\260\345\237\272e2e\351\252\214\346\224\266.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\345\220\216\347\273\255\344\274\230\345\214\226\350\267\257\347\272\277\345\233\276-2026-08-21.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\345\220\216\347\273\255\344\274\230\345\214\226\350\267\257\347\272\277\345\233\276-\346\211\247\350\241\214\346\200\273\347\273\223-2026-08-21.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\345\267\245\344\275\234\346\240\221\345\257\271\350\264\246\344\270\216\345\210\206\347\273\204\346\217\220\344\272\244\350\256\241\345\210\222-2026-08-21.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\346\210\277\351\227\264\344\272\213\344\273\266GC\344\270\216\345\275\222\346\241\243\345\217\243\345\276\204.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\346\236\266\346\236\204\345\215\207\347\272\247\346\226\271\346\241\210-MinIO\346\214\201\344\271\205\345\214\226\344\270\216Case\350\247\243\350\200\246\345\217\212L4\345\211\215\347\275\256\346\224\266\345\260\276.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\346\241\206\346\236\266\346\226\207\346\241\243v3\345\244\215\345\256\241\351\227\256\351\242\230\346\270\205\345\215\225.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\346\241\206\346\236\266\347\216\260\347\212\266\345\205\250\346\231\257\344\270\216\344\274\230\345\214\226\347\202\271_2026-08-21.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\346\265\213\350\257\225quarantine-burn-down-2026-08-21.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\350\203\275\345\212\233\345\222\250\350\257\242\350\257\257\345\205\245\346\216\245\345\215\225\346\265\201\347\250\213-\344\273\243\347\240\201\350\260\203\347\240\224\346\212\245\345\221\212_2026-08-21.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\350\203\275\345\212\233\345\222\250\350\257\242\350\257\257\345\205\245\346\216\245\345\215\225\346\265\201\347\250\213-\344\273\243\347\240\201\350\260\203\347\240\224\346\217\220\347\244\272\350\257\215.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\350\203\275\345\212\233\345\222\250\350\257\242\350\257\257\345\205\245\346\216\245\345\215\225\346\265\201\347\250\213-\350\260\203\347\240\224\346\240\270\345\257\271\344\270\216\344\277\256\345\244\215\345\256\236\346\226\275\350\256\241\345\210\222.md"
 D "docs/info/26.8.21/\345\215\217\344\275\234\345\256\244\350\236\215\345\220\210ClaudeScience\350\256\276\350\256\241\347\220\206\345\277\265\350\257\204\344\274\260\344\270\216\345\256\236\346\226\275\346\226\271\346\241\210.md"
 D "docs/info/26.8.22/CygnusX\350\256\260\345\277\206\346\250\241\345\235\227\344\274\230\345\214\226\345\256\236\346\226\275\346\211\213\345\206\214.md"
 D "docs/info/26.8.22/Screenshot 2026-08-22 at 15.44.31.png"
 D "docs/info/26.8.22/Screenshot 2026-08-22 at 18.43.49.png"
 D "docs/info/26.8.22/agentteams/image copy.png"
 D docs/info/26.8.22/agentteams/image.png
 D "docs/info/26.8.22/agentteams/\345\215\217\344\275\234\345\256\244\344\270\244\351\241\271\351\234\200\346\261\202\346\226\275\345\267\245\344\273\273\345\212\241\344\271\246_2026-08-22 copy.md"
 D "docs/info/26.8.22/agentteams/\345\215\217\344\275\234\345\256\244\344\270\244\351\241\271\351\234\200\346\261\202\346\226\275\345\267\245\344\273\273\345\212\241\344\271\246_2026-08-22.md"
 D "docs/info/26.8.22/agentteams/\345\215\217\344\275\234\345\256\244\346\234\200\347\273\210\346\236\266\346\236\204\345\256\241\346\240\270\346\204\217\350\247\201_2026-08-22.md"
 D "docs/info/26.8.22/agentteams/\345\215\217\344\275\234\345\256\244\351\202\200\350\257\267\346\210\220\345\221\230\344\270\216\345\210\206\346\236\220\350\277\207\347\250\213\350\256\260\345\275\225\345\244\215\347\216\260\350\260\203\347\240\224_2026-08-22.md"
 D "docs/info/26.8.22/agentteams/\345\273\272\350\256\256\344\272\214\350\277\207\347\250\213\350\256\260\345\275\225\347\216\260\347\212\266\350\260\203\346\237\245\344\273\273\345\212\241\344\271\246_2026-08-22.md"
 D "docs/info/26.8.22/agentteams/\345\273\272\350\256\256\344\272\214\350\277\207\347\250\213\350\256\260\345\275\225\347\216\260\347\212\266\350\260\203\346\237\245\346\212\245\345\221\212_2026-08-22.md"
 D "docs/info/26.8.22/image copy 2.png"
 D "docs/info/26.8.22/image copy 3.png"
 D "docs/info/26.8.22/image copy 4.png"
 D "docs/info/26.8.22/image copy 5.png"
 D "docs/info/26.8.22/image copy 6.png"
 D "docs/info/26.8.22/image copy 7.png"
 D "docs/info/26.8.22/image copy.png"
 D docs/info/26.8.22/image.png
 D docs/info/26.8.22/pdf_fix.md
 D docs/info/26.8.22/pdf_inspect.md
 D docs/info/26.8.22/pdf_inspection_report_2026-08-22.md
 D "docs/info/26.8.22/\345\210\206\346\236\220\350\256\241\345\210\222\345\215\241\347\211\207\350\247\206\350\247\211\344\270\216\344\272\244\344\272\222\344\274\230\345\214\226\345\256\236\347\216\260\350\256\241\345\210\222.md"
 D "docs/info/26.8.22/\345\211\215\347\253\257\347\273\204\344\273\266\350\247\204\350\214\203-Plan\345\210\206\346\236\220\350\256\241\345\210\222\345\215\241\347\211\207.md"
 D "docs/info/26.8.22/\345\215\217\344\275\234\345\256\244L4\350\256\260\345\277\206\346\216\245\345\205\245\347\216\260\347\212\266\350\260\203\347\240\224\346\212\245\345\221\212.md"
 D "docs/info/26.8.22/\345\215\217\344\275\234\345\256\244L4\350\256\260\345\277\206\346\216\245\345\205\245\347\216\260\347\212\266\350\260\203\347\240\224\346\217\220\347\244\272\350\257\215.md"
 D "docs/info/26.8.22/\345\215\217\344\275\234\345\256\244\346\241\206\346\236\266\346\226\207\346\241\243v4\345\244\215\345\256\241\347\273\223\350\256\272-2026-08-22.md"
 D "docs/info/26.8.22/\350\256\260\345\277\206\347\263\273\347\273\237\347\273\210\351\252\214\344\270\216\346\224\266\345\217\243\345\276\205\345\212\236-2026-08-22.md"
 D docs/info/26.8.23/APScheduler.md
 D "docs/info/26.8.23/CygnusX\346\236\266\346\236\204\346\255\242\346\215\237\344\270\216Runtime\347\273\237\344\270\200\344\274\230\345\214\226\346\226\271\346\241\210_2026-08-23.md"
 D "docs/info/26.8.23/CygnusX\346\236\266\346\236\204\346\255\242\346\215\237\344\270\216Runtime\347\273\237\344\270\200\344\274\230\345\214\226\346\226\271\346\241\210_\344\277\256\350\256\242\347\211\210_2026-08-23.md"
 D "docs/info/26.8.23/CygnusX\346\236\266\346\236\204\350\260\203\346\237\245\346\212\245\345\221\212_AI\346\227\245\347\250\213\347\256\241\347\220\206\344\270\216\346\217\220\351\206\222\347\263\273\347\273\237_2026-08-23.md"
 D "docs/info/26.8.23/CygnusX\346\262\231\347\256\261\345\256\211\345\205\250\345\212\240\345\233\272\345\256\236\346\226\275\346\211\213\345\206\214_Codex\346\226\275\345\267\245\347\211\210.md"
 D docs/info/26.8.23/Explorer_desion.md
 D "docs/info/26.8.23/Loop Engineering\344\270\216Skill\350\256\276\350\256\241\345\256\241\350\256\241\346\212\245\345\221\212_2026-08-23.md"
 D "docs/info/26.8.23/Screenshot 2026-08-23 at 17.20.23.png"
 D docs/info/26.8.23/sanbox.md
 D docs/info/26.8.23/sanbox_update.md
 D "docs/info/26.8.24/image copy 2.png"
 D "docs/info/26.8.24/image copy 3.png"
 D "docs/info/26.8.24/image copy 4.png"
 D "docs/info/26.8.24/image copy 5.png"
 D "docs/info/26.8.24/image copy 6.png"
 D "docs/info/26.8.24/image copy 7.png"
 D "docs/info/26.8.24/image copy 8.png"
 D "docs/info/26.8.24/image copy 9.png"
 D "docs/info/26.8.24/image copy.png"
 D docs/info/26.8.24/image.png
 D "docs/info/26.8.25/image copy 2.png"
 D "docs/info/26.8.25/image copy 3.png"
 D "docs/info/26.8.25/image copy 4.png"
 D "docs/info/26.8.25/image copy 5.png"
 D "docs/info/26.8.25/image copy.png"
 D docs/info/26.8.25/image.png
 D "docs/info/26.8.26/Screenshot 2026-08-26 at 20.41.03.png"
 D docs/info/26.8.26/bug_1
 D "docs/info/26.8.26/image copy 2.png"
 D "docs/info/26.8.26/image copy 3.png"
 D "docs/info/26.8.26/image copy 4.png"
 D "docs/info/26.8.26/image copy.png"
 D docs/info/26.8.26/image.png
 D "docs/info/26.8.26/\345\215\217\344\275\234\345\256\244\350\267\250Agent\346\266\210\346\201\257\344\272\222\351\200\232\344\274\230\345\214\226\345\256\236\346\226\275\346\211\213\345\206\214.md"
 D "docs/info/26.8.27/Screenshot 2026-08-27 at 09.16.55.png"
 D "docs/info/26.8.27/image copy 2.png"
 D "docs/info/26.8.27/image copy 3.png"
 D "docs/info/26.8.27/image copy.png"
 D docs/info/26.8.27/image.png
 D "docs/info/26.9.11/image copy 2.png"
 D "docs/info/26.9.11/image copy.png"
 D docs/info/26.9.11/image.png
 D "docs/info/26.9.15/image copy.png"
 D docs/info/26.9.15/image.png
 D "docs/info/26.9.16/agent\345\256\271\345\231\250\346\235\203\351\231\220\344\270\216\351\225\234\345\203\217\351\205\215\347\275\256\346\243\200\346\237\245\344\274\230\345\214\226\346\270\205\345\215\225.md"
 D "docs/info/26.9.16/image copy 2.png"
 D "docs/info/26.9.16/image copy 3.png"
 D "docs/info/26.9.16/image copy 4.png"
 D "docs/info/26.9.16/image copy.png"
 D docs/info/26.9.16/image.png
 D docs/info/26.9.17/2026-09-17_21.29.33.png
 D docs/info/26.9.17/2026-09-17_21.34.54.png
 D docs/info/26.9.17/2026-09-17_21.43.22.png
 D "docs/info/26.9.17/image copy 2.png"
 D "docs/info/26.9.17/image copy 3.png"
 D "docs/info/26.9.17/image copy 4.png"
 D "docs/info/26.9.17/image copy 5.png"
 D "docs/info/26.9.17/image copy 6.png"
 D "docs/info/26.9.17/image copy.png"
 D docs/info/26.9.17/image.png
 D docs/info/26.9.18/2026-09-18_10.11.32.png
 D docs/info/26.9.18/2026-09-18_14.02.23.png
 D "docs/info/26.9.18/OmicHub\347\247\221\347\240\224\351\227\255\347\216\257-\345\256\236\346\226\275\346\211\213\345\206\214.md"
 D "docs/info/26.9.18/OmicHub\347\247\221\347\240\224\351\227\255\347\216\257-\347\216\260\347\212\266\350\260\203\346\237\245\344\273\273\345\212\241\344\271\246.md"
 D "docs/info/26.9.18/OmicHub\347\247\221\347\240\224\351\227\255\347\216\257-\347\216\260\347\212\266\350\260\203\346\237\245\346\212\245\345\221\212.md"
 D "docs/info/26.9.18/image copy 2.png"
 D "docs/info/26.9.18/image copy 3.png"
 D "docs/info/26.9.18/image copy 4.png"
 D "docs/info/26.9.18/image copy 5.png"
 D "docs/info/26.9.18/image copy.png"
 D docs/info/26.9.18/image.png
 D docs/info/26.9.18/omichub-vs-openai4s-comparison-report.md
 D docs/info/26.9.18/remote-and-notebook-run-map.md
 D docs/info/26.9.19/agent_execution_framework_update.md
 D docs/info/26.9.19/ai_bug.md
 D "docs/info/26.9.19/image copy 2.png"
 D "docs/info/26.9.19/image copy 3.png"
 D "docs/info/26.9.19/image copy 4.png"
 D "docs/info/26.9.19/image copy 5.png"
 D "docs/info/26.9.19/image copy 6.png"
 D "docs/info/26.9.19/image copy 7.png"
 D "docs/info/26.9.19/image copy 8.png"
 D "docs/info/26.9.19/image copy.png"
 D docs/info/26.9.19/image.png
 D "docs/info/26.9.2/image copy 2.png"
 D "docs/info/26.9.2/image copy 3.png"
 D "docs/info/26.9.2/image copy 4.png"
 D "docs/info/26.9.2/image copy 5.png"
 D "docs/info/26.9.2/image copy 6.png"
 D "docs/info/26.9.2/image copy 7.png"
 D "docs/info/26.9.2/image copy.png"
 D docs/info/26.9.2/image.png
 D "docs/info/26.9.2/\346\210\252\345\261\2172026-09-04 09.24.09.png"
 D docs/info/26.9.20/2026-09-20_18.42.12.png
 D docs/info/26.9.20/2026-09-20_22.33.54.png
 D "docs/info/26.9.20/2026-09-20\342\200\224\342\200\22414.45.27.png"
 D "docs/info/26.9.20/image copy 10.png"
 D "docs/info/26.9.20/image copy 11.png"
 D "docs/info/26.9.20/image copy 2.png"
 D "docs/info/26.9.20/image copy 3.png"
 D "docs/info/26.9.20/image copy 4.png"
 D "docs/info/26.9.20/image copy 5.png"
 D "docs/info/26.9.20/image copy 6.png"
 D "docs/info/26.9.20/image copy 7.png"
 D "docs/info/26.9.20/image copy 8.png"
 D "docs/info/26.9.20/image copy 9.png"
 D "docs/info/26.9.20/image copy.png"
 D docs/info/26.9.20/image.png
 D "docs/info/26.9.21/MAS\345\256\236\346\226\275_\351\230\266\346\256\2650-4\345\256\214\346\210\220\346\212\245\345\221\212.md"
 D "docs/info/26.9.21/MAS\345\256\236\346\226\275_\351\230\266\346\256\2650\345\267\256\345\274\202\346\270\205\345\215\225.md"
 D "docs/info/26.9.21/image copy 2.png"
 D "docs/info/26.9.21/image copy.png"
 D docs/info/26.9.21/image.png
 D docs/info/26.9.21/web_s.md
 D "docs/info/26.9.21/\347\224\237\347\211\251\344\277\241\346\201\257\351\203\250\351\227\250\351\241\265\351\235\242_MAS\346\234\200\345\260\217\345\256\236\347\216\260\345\256\236\346\226\275\346\211\213\345\206\214.md"
 D docs/info/26.9.22/2026-09-22_09.27.52.png
 D docs/info/26.9.22/api_routes_full.tsv
 D "docs/info/26.9.22/image copy 2.png"
 D "docs/info/26.9.22/image copy.png"
 D docs/info/26.9.22/image.png
 D docs/info/26.9.23/context-pipeline-investigation-report.md
 D docs/info/26.9.23/flowagent_mvp_implementation_plan.md
 D docs/info/26.9.23/migration-spec-openai4s-to-omichub.md
 D docs/info/26.9.23/prompt-omichub-investigation.md
 D docs/info/26.9.23/session-management.md
 D docs/info/26.9.23/snakemake_agent_integration_survey_prompt.md
 D docs/info/26.9.23/snakemake_agent_integration_survey_report.md
 D docs/info/26.9.25/image.png
 D docs/info/26.9.25/openai4s-long-conversation-architecture.md
 D "docs/info/26.9.29/image copy 2.png"
 D "docs/info/26.9.29/image copy 3.png"
 D "docs/info/26.9.29/image copy 4.png"
 D "docs/info/26.9.29/image copy.png"
 D docs/info/26.9.29/image.png
 D "docs/info/26.9.29/\346\231\272\350\203\275\344\275\223\351\200\211\346\213\251\345\274\271\347\252\227\351\207\215\346\236\204-\345\256\236\347\216\260\350\256\241\345\210\222.md"
 D docs/info/26.9.30/agent_governance_code_audit.md
 D docs/info/26.9.30/image.png
 D "docs/info/26.9.4/image copy 2.png"
 D "docs/info/26.9.4/image copy.png"
 D docs/info/26.9.4/image.png
 D "docs/info/26.9.4/\345\273\272\350\256\256\350\277\275\351\227\256Chips\345\212\237\350\203\275\345\256\236\347\216\260\350\256\241\345\210\222.md"
 D "docs/info/26.9.7/image copy 2.png"
 D "docs/info/26.9.7/image copy.png"
 D docs/info/26.9.7/image.png
 M flows/atac_seq.yaml
 M flows/rna_seq.yaml
 M frontend/package.json
 M frontend/src/api/datasets.ts
 M frontend/src/api/researchAgent.ts
 M frontend/src/components/research/__tests__/TreasureSessionIsolation.test.ts
 M frontend/src/views/ProjectDetailView.vue
 M frontend/src/views/TreasureMouseView.vue
 M frontend/vite.config.js
 M frontend/vite.config.ts
 M mcp-server/ARCHITECTURE.md
 M mcp-server/client/api_client.py
 M mcp-server/config.yaml
 M mcp-server/core/config.py
 M mcp-server/tools.yaml
 M mcp-server/tools/analysis.py
 M mcp-server/tools/flows.py
 M mcp-server/tools/pipelines.py
 m pipelines/ATACFlow
 m pipelines/RNAFlow
 m pipelines/Treasure-Seeking_Mouse
 m pipelines/tools
 M src/cygnusx/api/v1/ai.py
 M src/cygnusx/api/v1/datasets.py
 M src/cygnusx/api/v1/research_agent.py
 M src/cygnusx/api/v1/router.py
 M src/cygnusx/application/schemas/agent_tools.py
 M src/cygnusx/application/schemas/research_agent.py
 M src/cygnusx/application/services/agent_service.py
 M src/cygnusx/application/services/agent_tool_gateway.py
 M src/cygnusx/application/services/analysis_flow_tool_service.py
 M src/cygnusx/application/services/dataset_analysis_service.py
 M src/cygnusx/application/services/dataset_import_service.py
 M src/cygnusx/application/services/flow_service.py
 M src/cygnusx/application/services/pipeline_controller.py
 M src/cygnusx/application/services/research_treasure_service.py
 M src/cygnusx/application/services/tool_bridge_service.py
 M src/cygnusx/application/services/tool_confirmation_service.py
 M src/cygnusx/core/config.py
 M src/cygnusx/domain/flow/submission_validator.py
 M src/cygnusx/domain/flow/value_objects.py
 M src/cygnusx/infrastructure/database/models/__init__.py
 M src/cygnusx/infrastructure/mcp/pipeline_preset.py
 M src/cygnusx/infrastructure/mcp/presets.py
 M src/cygnusx/tools/flow_schema_compiler.py
 M src/cygnusx/tools/schema_loader.py
 M tests/unit/test_dataset_gateway_phase3.py
 M tests/unit/test_dataset_phase3_review.py
 M tool_configs/tools_schema.yaml
?? ARCHITECTURE_DESIGN/CygnusX_research_plan_architecture.md
?? ARCHITECTURE_DESIGN/CygnusX_treasure_mouse_architecture.md
?? alembic/versions/bioopsphase5_research_plans.py
?? benchmarks/
?? docs/adr/phase5-governed-research-agent-orchestration.md
?? docs/adr/treasure-agent-shared-tools-and-delivery.md
?? docs/adr/treasure-native-entry-and-capabilities.md
?? docs/adr/treasure-react-island-poc.md
?? docs/audits/cygnusx-phase5-acceptance.md
?? docs/audits/cygnusx-phase5-changes.md
?? docs/audits/cygnusx-phase5-entry-gates.md
?? docs/audits/cygnusx-phase5-implementation-report.md
?? docs/audits/cygnusx-treasure-mouse-ui-regression-and-mcp-integration-audit-2026-10-15.md
?? docs/audits/treasure-e2e-release-gates.md
?? docs/contracts/cygnusx-research-artifact-cell-v1.schema.json
?? docs/contracts/cygnusx-research-claim-input-v1.schema.json
?? docs/contracts/cygnusx-research-claim-v1.schema.json
?? docs/contracts/cygnusx-research-plan-input-v1.schema.json
?? docs/contracts/cygnusx-research-plan-v1.md
?? docs/contracts/cygnusx-research-plan-v1.schema.json
?? docs/contracts/treasure-research-actions-v1.md
?? docs/contracts/treasure-research-event-projection-v1.md
?? docs/contracts/treasure-research-message-v1.md
?? docs/design/cygnusx-project-traceable-export-and-reproduction.md
?? docs/implementation/CygnusX_TreasureMouse_End_to_End_Implementation_2026-10-16.md
?? docs/implementation/treasure-e2e-w0-baseline.md
?? docs/implementation/treasure-full-presentation-migration.md
?? docs/implementation/treasure-mouse-e2e-research-workflow-implementation.md
?? docs/implementation/treasure-native-entry-reload-fix.md
?? docs/implementation/treasure-native-p0-access-and-entry.md
?? docs/implementation/treasure-native-refresh-404-fix.md
?? docs/implementation/treasure-native-screenshot-style-alignment.md
?? docs/implementation/treasure-react-island-poc.md
?? docs/info/old_info/
?? docs/runbooks/cygnusx-phase5-rollback.md
?? evidence/phase5/
?? evidence/treasure-e2e/
?? evidence/treasure-native/
?? frontend/poc/
?? frontend/scripts/
?? frontend/src/api/researchPlans.ts
?? frontend/src/components/ResearchPlanWorkbench.vue
?? frontend/src/components/research/TreasureBrandMark.vue
?? frontend/src/components/research/TreasureOriginalDisplay.vue
?? frontend/src/components/research/__tests__/ResearchPlanWorkbench.test.ts
?? frontend/src/components/research/__tests__/TreasureAccess.test.ts
?? frontend/src/components/research/__tests__/TreasureOriginalEntry.test.ts
?? frontend/src/components/research/adapters/
?? frontend/src/components/research/treasureIslandLoader.ts
?? frontend/src/types/treasureIsland.d.ts
?? frontend/src/views/TreasureResearchWorkbench.vue
?? frontend/src/views/__tests__/ProjectDetailResearchContext.test.ts
?? scripts/analyze_research_benchmark.py
?? scripts/evaluate_research_benchmark.py
?? scripts/export_research_plan_contracts.py
?? scripts/poc/check-treasure-island.sh
?? scripts/poc/treasure-island-browser.mjs
?? src/cygnusx/api/v1/research_claims.py
?? src/cygnusx/api/v1/research_plans.py
?? src/cygnusx/application/schemas/research_claims.py
?? src/cygnusx/application/schemas/research_plan.py
?? src/cygnusx/application/services/research_claim_service.py
?? src/cygnusx/application/services/research_plan_service.py
?? src/cygnusx/domain/flow/validation_plugins.py
?? src/cygnusx/domain/research/
?? src/cygnusx/infrastructure/database/models/research_plan.py
?? tests/unit/test_fixed_flow_tools_api.py
?? tests/unit/test_flow_contract_drift.py
?? tests/unit/test_flow_validation_parity.py
?? tests/unit/test_legacy_pipeline_tools_gate.py
?? tests/unit/test_research_benchmark_phase5.py
?? tests/unit/test_research_claim_artifact_phase5.py
?? tests/unit/test_research_plan_gateway_phase5.py
?? tests/unit/test_research_plan_phase5.py
?? tests/unit/test_research_plan_storage_phase5.py
?? tests/unit/test_research_science_phase5.py
?? tests/unit/test_treasure_native_access.py
?? tests/unit/tools/test_fixed_flow_bridge.py
```

```text
977ad657bbe7d49f2200a5f3f550b70f25234f3d Protocol/FlowFrame (heads/main)
 4a68b347ba3b9497a86eed2603b6577afc3c2f27 pipelines/ATACFlow (heads/main)
 b351e03dfc845d229102d90f9bd88d6ca731f0de pipelines/EBIDownload (v1.4.0-2-gb351e03)
 19f5068c4f9370ea27cb6fe554a3f061a1b62a51 pipelines/RNAFlow (heads/feat/result-manifest)
 88dae95e7294dea5004330203f56e4211776fd74 pipelines/Treasure-Seeking_Mouse (heads/gitcode-sync)
 b5066338fba47b1ed3fbee042f1cb43859cff882 pipelines/scrna (heads/main)
 24ecb6ce75657c5ce188603b54ac7bf10ffb6d46 pipelines/tools (heads/main)
```

独立 `/home/zj/zj_code_libarary/EBIDownload`：HEAD `a46f89b4fcc44c3685cbb9d61c32461dd1211a34`，status 空，remote `X_polariseq.git`，CLI crate 1.4.3。平台子模块 remote `EBIDownload.git`，CLI crate 1.4.0，status 空。仅旁仓源码，不证明部署。

## H01–H05 本地只读探针

- H01：`/data/omichub/bin/EBIDownload --version` → `ebidownload-cli 1.4.0`。SHA-256：`6628ad8fd489eee68b9ebd58299f32c021812b386435a82193911c4494e219c4`。仅宿主。
- H02：同一二进制 `download --help` → download method `ftp,prefetch,aws,auto`；支持 progress-port/write-progress-key；无 aspera。只运行帮助，不调用 download/dry-run。
- H03：`docker ps --format ...` → socket `operation not permitted`。未查看任何容器环境、生产日志或执行容器命令；镜像 digest/容器版本/UID/挂载均 UNKNOWN。
- H04：当前进程 Settings 白名单：enable_ebi_download=true；enable_direct_download=false；enable_cloud_storage_download=false；tool_gateway_read_enabled=false；dataset_discovery_readonly=false；dataset_import_write=false；agent_download_write_enabled=false；task_queue_backend=celery。不是运行容器配置。YAML 三个 features 均 false，API 用 YAML OR Settings。
- H05：宿主 `/usr/bin/aria2c` 不存在；配置的 ossutil/obsutil 是顶层路径，磁盘列表为带版本子目录；tosutil 顶层存在。目录名不当成工具版本或可执行证明。未读取云商凭据/配置内容。

## I01–I04 测试与纯 DTO 探针

```bash
.venv/bin/python -m pytest tests/unit/test_download_service.py tests/unit/test_dataset_geo_validation.py tests/unit/test_dataset_import_handoff.py tests/unit/test_dataset_gateway_phase3.py tests/unit/test_phase0b_confirmation.py tests/unit/test_mcp_dual_surface_parity.py -q -m "not quarantine" -p no:cacheprovider
```
I01：70 collected，65 passed，5 deselected，1 pydantic deprecation warning。排除的五项为旧 DownloadService fixture 访问已删除 `_settings`。三项实际执行下载单测只覆盖 DTO / argv，不覆盖 Worker。
```bash
.venv/bin/python -m pytest tests/unit/test_agent_tools_phase2.py -q -p no:cacheprovider
```
I02：39 collected，38 passed，1 failed。失败 `test_dynamic_mcp_registry_bridge_and_gateway_share_contract`，`schema_loader.py:195` 读取 fixture SimpleNamespace 缺少 `legacy_pipeline_tools`，在 preset 构建时中止；不能声称动态 MCP→Gateway 全绿。没有修测试或业务代码。
I03：纯 DownloadRequest 构造：`ftps://example.org/a` REJECT；重复 HTTPS 列表 ACCEPT；`http://2130706433/a` ACCEPT；`oss://127.0.0.1/a` REJECT；`oss://[::1]/a`、`oss://2130706433/a` ACCEPT。只做内存校验，没有 DNS/网络/任务副作用，不能当作 SSRF 实际利用成功。
I04：测试隔离机制：GEO 用 httpx.MockTransport；Dataset 使用 sqlite:// + async facade、临时目录；确认服务为 memory/fake Redis；future execute 路径用 monkeypatch 解除测试内门禁并替换 DownloadService.submit。`test_dataset_import_handoff.py:207` 的 double 主动写 task_id/source，真实 Worker 没有写；因此其通过不能证明真实契约兼容。

未运行：真实下载/云盘提取/HTTP 公网请求/FTP/生产 API/迁移/容器任务/前端浏览器 E2E。没有安装依赖、更新锁文件、提交、推送或部署。

## 补充证据：已存在统一FileRegistry与processed归档链

| ID | 路径 | SHA-256 | 函数定位 |
|---|---|---|---|
| E46 | `src/cygnusx/application/services/geo_processed_data_service.py` | `20834f004c0ffacff9f9602f32b31958657188ceaf6ea388b6e3a00db07f5d85` | 31: class GeoProcessedDataService:<br>32: def __init__(self, db: AsyncSession, registry: FileRegistry | None = None) -> None:<br>38: def candidates(candidate: dict[str, Any]) -> dict[str, Any]:<br>65: async def expand( |
| E47 | `src/cygnusx/infrastructure/storage/file_registry.py` | `2e54d6ccffa66221bd74f6dea9cf971d35f28a4506d21ddd5064f8e34d592dcb` | 53: def _detect_file_type(filename: str) -> FileType:<br>61: class FileRegistry:<br>64: def __init__(<br>74: async def register(<br>134: async def register_directory(<br>187: async def get_or_register(<br>196: async def _find_by_path( |
| E48 | `src/cygnusx/api/v1/ai.py` | `63d9e11867a63b219bb12e85a4f582b7ccd1b5df409d653819cc768292e9d7e7` | 42: async def create_external_tool_confirmation(<br>62: def get_ai_service(db: DbSession) -> AIService:<br>70: async def ai_status(db: DbSession) -> dict[str, bool]:<br>87: async def list_conversations(<br>99: async def create_conversation(<br>112: async def get_conversation(<br>121: async def delete_conversation(<br>131: async def ai_websocket(websocket: WebSocket) -> None:<br>208: async def approve_tool_confirmation(<br>233: async def reject_tool_confirmation(<br>256: class FlowPrepareRequest(BaseModel):<br>263: async def prepare_analysis_flow(<br>293: async def submit_analysis_flow(<br>318: async def approve_tool_invocation(<br>344: async def reject_tool_invocation( |
| E49 | `deploy/docker/docker-compose.yml` | `3be0c41dd269931dd41ca6b539550a718d41fcf85701383d484987a53a2aee81` |  |
| E50 | `deploy/docker/worker-entrypoint.sh` | `f65a2bb56b74eb69f08efd5e6d882591ab570406ab438d6609f2a83a77e655a5` |  |

I05：`.venv/bin/python -m pytest tests/unit/test_dataset_phase3_review.py -q -p no:cacheprovider` → 8 passed，1 pydantic warning。仍为SQLite/临时文件/替代确认与任务提交，非真实Worker；其中 `test_processed_archive_reuses_real_file_registry_and_preserves_parent` 调用真实 FileRegistry 验证原archive保留与子资产parent SHA；reconciler closed gate用例验证不创建DB engine。累计111 passed / 1 failed / 5 deselected（112实际执行断言用例结果）。
