--
-- PostgreSQL database dump
--

\restrict 2aEfLby7y9z4qRoBwNDbTDlUB8m6SodnNsfzVYm23cF4xiK0Kxb5UTzVYcoVIEy

-- Dumped from database version 14.23 (Debian 14.23-1.pgdg12+1)
-- Dumped by pg_dump version 14.23 (Debian 14.23-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: cygnusx_project_export_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.cygnusx_project_export_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            IF NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.project_id IS DISTINCT FROM OLD.project_id
            OR NEW.request_key IS DISTINCT FROM OLD.request_key OR NEW.manifest_digest IS DISTINCT FROM OLD.manifest_digest
            OR NEW.manifest::text IS DISTINCT FROM OLD.manifest::text THEN
                RAISE EXCEPTION 'Frozen project export scope cannot change';
            END IF;
            RETURN NEW;
        END; $$;


--
-- Name: cygnusx_project_report_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.cygnusx_project_report_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF NEW.user_id::text IS DISTINCT FROM OLD.user_id::text OR NEW.project_id::text IS DISTINCT FROM OLD.project_id::text OR NEW.source_manifest_job_id::text IS DISTINCT FROM OLD.source_manifest_job_id::text OR NEW.request_key::text IS DISTINCT FROM OLD.request_key::text OR NEW.source_digest::text IS DISTINCT FROM OLD.source_digest::text OR NEW.source_snapshot::text IS DISTINCT FROM OLD.source_snapshot::text OR NEW.parent_id::text IS DISTINCT FROM OLD.parent_id::text OR NEW.version::text IS DISTINCT FROM OLD.version::text THEN RAISE EXCEPTION 'Frozen project report identity cannot change'; END IF; RETURN NEW; END; $$;


--
-- Name: cygnusx_project_report_publication_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.cygnusx_project_report_publication_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF OLD.status = 'ready' AND ROW(NEW.status,NEW.archive_path,NEW.html_file_record_id,NEW.html_sha256,NEW.html_size,NEW.pdf_file_record_id,NEW.pdf_sha256,NEW.pdf_size,NEW.pdf_status) IS DISTINCT FROM ROW(OLD.status,OLD.archive_path,OLD.html_file_record_id,OLD.html_sha256,OLD.html_size,OLD.pdf_file_record_id,OLD.pdf_sha256,OLD.pdf_size,OLD.pdf_status) THEN RAISE EXCEPTION 'Published project report cannot change'; END IF; RETURN NEW; END; $$;


--
-- Name: cygnusx_reject_result_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.cygnusx_reject_result_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'Result observations are immutable'; END; $$;


--
-- Name: cygnusx_research_plan_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.cygnusx_research_plan_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
                IF NEW.user_id IS DISTINCT FROM OLD.user_id
                   OR NEW.project_id IS DISTINCT FROM OLD.project_id
                   OR NEW.series_id IS DISTINCT FROM OLD.series_id
                   OR NEW.version IS DISTINCT FROM OLD.version
                   OR NEW.request_key IS DISTINCT FROM OLD.request_key
                   OR NEW.draft::text IS DISTINCT FROM OLD.draft::text
                   OR NEW.digest IS DISTINCT FROM OLD.digest THEN
                    RAISE EXCEPTION 'Research intent is immutable; create a new version';
                END IF;
                RETURN NEW;
            END; $$;


--
-- Name: reject_report_snapshot_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.reject_report_snapshot_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION 'report snapshots are immutable';
        END;
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_goal_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_goal_events (
    id uuid NOT NULL,
    goal_id uuid NOT NULL,
    sequence integer NOT NULL,
    event_type character varying(64) NOT NULL,
    dedupe_key character varying(256),
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agent_goal_work_units; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_goal_work_units (
    id uuid NOT NULL,
    goal_id uuid NOT NULL,
    work_unit_key character varying(128) NOT NULL,
    kind character varying(32) DEFAULT 'llm_step'::character varying NOT NULL,
    title character varying(256) NOT NULL,
    instruction text NOT NULL,
    depends_on jsonb DEFAULT '[]'::jsonb NOT NULL,
    owner_agent_id character varying(128),
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    attempt integer DEFAULT 0 NOT NULL,
    input_ref jsonb DEFAULT '{}'::jsonb NOT NULL,
    output_ref jsonb DEFAULT '{}'::jsonb NOT NULL,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    idempotency_key character varying(256) NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agent_goals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_goals (
    id uuid NOT NULL,
    session_id character varying(50),
    user_id uuid NOT NULL,
    workspace_id uuid,
    manager_agent_id character varying(128) NOT NULL,
    objective text NOT NULL,
    success_criteria jsonb DEFAULT '[]'::jsonb NOT NULL,
    mode character varying(32) DEFAULT 'chat'::character varying NOT NULL,
    permission character varying(32) DEFAULT 'safe'::character varying NOT NULL,
    status character varying(32) DEFAULT 'draft'::character varying NOT NULL,
    plan_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    turn_count integer DEFAULT 0 NOT NULL,
    max_turns integer DEFAULT 20 NOT NULL,
    token_budget integer,
    tokens_used integer DEFAULT 0 NOT NULL,
    deadline_at timestamp with time zone,
    event_sequence integer DEFAULT 0 NOT NULL,
    lease_owner character varying(128),
    lease_expires_at timestamp with time zone,
    version integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agent_memories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_memories (
    id uuid NOT NULL,
    user_id character varying(50) NOT NULL,
    agent_id character varying(50),
    scope character varying(16) NOT NULL,
    content text NOT NULL,
    keywords jsonb DEFAULT '[]'::jsonb NOT NULL,
    source_session character varying(50),
    confidence double precision DEFAULT '1'::double precision NOT NULL,
    use_count integer DEFAULT 0 NOT NULL,
    last_used_at timestamp with time zone,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    embedding public.vector(1024),
    embedding_model character varying(120),
    project_id character varying(64)
);


--
-- Name: agent_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_templates (
    id uuid NOT NULL,
    agent_id character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    description text NOT NULL,
    avatar character varying(10) NOT NULL,
    color character varying(20) NOT NULL,
    category character varying(50) NOT NULL,
    model_id uuid,
    model_engine character varying(100) NOT NULL,
    system_prompt text NOT NULL,
    welcome_message text NOT NULL,
    mcp_ids json NOT NULL,
    skill_ids json NOT NULL,
    temperature double precision NOT NULL,
    max_tokens integer NOT NULL,
    is_builtin boolean NOT NULL,
    is_active boolean NOT NULL,
    is_default boolean NOT NULL,
    created_by character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    model_name character varying(100) DEFAULT ''::character varying NOT NULL,
    features jsonb DEFAULT '{}'::jsonb NOT NULL,
    project_id character varying(64),
    model_tier character varying(16) DEFAULT 'auto'::character varying NOT NULL
);


--
-- Name: agent_tool_invocations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_tool_invocations (
    id uuid NOT NULL,
    owner_id character varying(50) NOT NULL,
    project_id character varying(64),
    conversation_id character varying(50) NOT NULL,
    agent_kind character varying(40) NOT NULL,
    capability_id character varying(100) NOT NULL,
    request_id character varying(80) NOT NULL,
    parameters_hash character varying(64) NOT NULL,
    confirmation_id character varying(128),
    task_id uuid,
    status character varying(40) NOT NULL,
    error_code character varying(80),
    preview json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agentteams_bridge_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agentteams_bridge_settings (
    id integer NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    bridge_url character varying(512) DEFAULT ''::character varying NOT NULL,
    manager_token text DEFAULT ''::text NOT NULL,
    data_steward_token text DEFAULT ''::text NOT NULL,
    approval_token text DEFAULT ''::text NOT NULL,
    workflow_operator_token text DEFAULT ''::text NOT NULL,
    timeout_seconds double precision DEFAULT '10'::double precision NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    element_url character varying(1024) NOT NULL
);


--
-- Name: agentteams_bridge_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agentteams_bridge_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agentteams_bridge_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agentteams_bridge_settings_id_seq OWNED BY public.agentteams_bridge_settings.id;


--
-- Name: agentteams_case_cursors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agentteams_case_cursors (
    id uuid NOT NULL,
    session_id character varying(50) NOT NULL,
    case_id character varying(80) NOT NULL,
    event_cursor character varying(128),
    notified_statuses jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: agentteams_room_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agentteams_room_members (
    id uuid NOT NULL,
    room_id character varying(80) NOT NULL,
    user_id character varying(50) NOT NULL,
    role character varying(20) DEFAULT 'member'::character varying NOT NULL,
    invited_by character varying(50) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    responded_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: agentteams_rooms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agentteams_rooms (
    id uuid NOT NULL,
    room_id character varying(80) NOT NULL,
    owner_id character varying(50) NOT NULL,
    title character varying(200) DEFAULT '协作室会话'::character varying NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    origin character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    case_id character varying(80),
    matrix_room_id character varying(128),
    proposal jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    origin_ref character varying(64),
    project_id character varying(64)
);


--
-- Name: agentteams_turn_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agentteams_turn_records (
    record_id uuid NOT NULL,
    case_id character varying(80) NOT NULL,
    work_item_id character varying(128) NOT NULL,
    round_number integer NOT NULL,
    call_seq integer NOT NULL,
    agent_id character varying(128) NOT NULL,
    actor_user_id character varying(50),
    requester_ref character varying(50),
    provider character varying(100) DEFAULT ''::character varying NOT NULL,
    model character varying(160) DEFAULT ''::character varying NOT NULL,
    prompt_tokens integer,
    completion_tokens integer,
    total_tokens integer,
    duration_ms integer DEFAULT 0 NOT NULL,
    status character varying(20) NOT NULL,
    s3_uri character varying(1024) NOT NULL,
    recorded_at timestamp with time zone NOT NULL
);


--
-- Name: ai_call_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_call_metrics (
    id uuid NOT NULL,
    provider character varying(64) NOT NULL,
    model character varying(128) NOT NULL,
    status character varying(16) NOT NULL,
    duration_ms double precision DEFAULT '0'::double precision NOT NULL,
    prompt_tokens integer DEFAULT 0 NOT NULL,
    completion_tokens integer DEFAULT 0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    session_id character varying(64),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: ai_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_conversations (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    model character varying(100) NOT NULL,
    summary text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    assistant_id character varying(50)
);


--
-- Name: ai_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_messages (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    tool_calls json NOT NULL,
    tool_call_id character varying(100),
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ai_metric_alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_metric_alerts (
    id uuid NOT NULL,
    rule character varying(64) NOT NULL,
    level character varying(20) DEFAULT 'warning'::character varying NOT NULL,
    message text NOT NULL,
    metric_value double precision DEFAULT '0'::double precision NOT NULL,
    threshold double precision DEFAULT '0'::double precision NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: ai_provider_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_provider_configs (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    provider_type character varying(30) NOT NULL,
    model character varying(100) NOT NULL,
    base_url character varying(500) NOT NULL,
    api_key text NOT NULL,
    temperature double precision NOT NULL,
    max_tokens integer NOT NULL,
    top_p double precision NOT NULL,
    timeout integer NOT NULL,
    is_active boolean NOT NULL,
    is_default boolean NOT NULL,
    extra_params json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    input_price double precision,
    output_price double precision,
    input_cache_price double precision,
    output_cache_price double precision,
    context_window integer DEFAULT 262144 NOT NULL,
    tier character varying(16) DEFAULT 'light'::character varying NOT NULL,
    cost_per_1m_in double precision,
    cost_per_1m_out double precision,
    latency_budget_ms integer,
    vendor character varying(64),
    weight integer DEFAULT 100 NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: announcements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.announcements (
    id uuid NOT NULL,
    title character varying(200) NOT NULL,
    description text NOT NULL,
    type character varying(20) DEFAULT 'info'::character varying NOT NULL,
    icon character varying(100),
    link character varying(500),
    button_text character varying(50),
    start_time timestamp with time zone NOT NULL,
    end_time timestamp with time zone,
    dismiss_behavior character varying(20) DEFAULT 'none'::character varying NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: COLUMN announcements.title; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.title IS '通知标题';


--
-- Name: COLUMN announcements.description; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.description IS '通知描述';


--
-- Name: COLUMN announcements.type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.type IS 'info/success/warning/feature';


--
-- Name: COLUMN announcements.icon; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.icon IS 'emoji 或 lucide 图标名';


--
-- Name: COLUMN announcements.link; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.link IS '跳转链接（站内路径或外链）';


--
-- Name: COLUMN announcements.button_text; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.button_text IS '按钮文字，默认「立即查看」';


--
-- Name: COLUMN announcements.start_time; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.start_time IS '生效开始时间';


--
-- Name: COLUMN announcements.end_time; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.end_time IS '生效结束时间，空则永久';


--
-- Name: COLUMN announcements.dismiss_behavior; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.dismiss_behavior IS 'daily/forever/none';


--
-- Name: COLUMN announcements.priority; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.priority IS '优先级，越大越优先';


--
-- Name: COLUMN announcements.is_enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.announcements.is_enabled IS '是否启用';


--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_keys (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    key_hash character varying(64) NOT NULL,
    key_prefix character varying(12) NOT NULL,
    scopes json DEFAULT '[]'::json NOT NULL,
    expires_at timestamp with time zone,
    last_used_at timestamp with time zone,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id uuid NOT NULL,
    user_id uuid,
    username character varying(100),
    method character varying(10) NOT NULL,
    path character varying(500) NOT NULL,
    resource_type character varying(50),
    resource_id character varying(100),
    status_code integer NOT NULL,
    ip character varying(64),
    user_agent character varying(500),
    detail json DEFAULT '{}'::json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: blast_databases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blast_databases (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    db_key character varying(64) NOT NULL,
    db_type character varying(16) NOT NULL,
    source_species character varying(128),
    source_version character varying(64),
    file_path character varying(512) NOT NULL,
    file_size_mb double precision NOT NULL,
    sequence_count integer NOT NULL,
    build_status character varying(32) NOT NULL,
    is_public boolean NOT NULL,
    created_by uuid,
    build_log text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    version_group character varying(64) NOT NULL,
    is_active boolean DEFAULT false NOT NULL
);


--
-- Name: blast_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blast_tasks (
    id uuid NOT NULL,
    task_id character varying(64) NOT NULL,
    user_id uuid NOT NULL,
    db_id uuid NOT NULL,
    program character varying(16) NOT NULL,
    query_title character varying(256),
    query_sequence text NOT NULL,
    query_file_path character varying(512),
    evalue double precision NOT NULL,
    max_target_seqs integer NOT NULL,
    word_size integer,
    gapopen integer,
    gapextend integer,
    status character varying(32) NOT NULL,
    progress integer NOT NULL,
    result_format character varying(16) NOT NULL,
    result_path character varying(512),
    result_size_kb integer,
    hit_count integer,
    top_hit_identity double precision,
    top_hit_evalue double precision,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    error_message text
);


--
-- Name: case_artifact_dependencies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.case_artifact_dependencies (
    id uuid NOT NULL,
    case_id character varying(80) NOT NULL,
    downstream_artifact_id character varying(512) NOT NULL,
    upstream_artifact_id character varying(512) NOT NULL,
    relation character varying(32) DEFAULT 'input_to'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: case_artifact_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.case_artifact_versions (
    id uuid NOT NULL,
    case_id character varying(80) NOT NULL,
    artifact_id character varying(512) NOT NULL,
    version_no integer NOT NULL,
    producing_event_id character varying(128),
    work_item_id character varying(128),
    checksum_sha256 character varying(64) NOT NULL,
    size_bytes integer NOT NULL,
    content_type character varying(255) DEFAULT ''::character varying NOT NULL,
    storage_uri character varying(1024) NOT NULL,
    environment_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: chat_assistants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_assistants (
    id integer NOT NULL,
    assistant_id character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    description character varying(500),
    system_prompt text NOT NULL,
    default_model_id uuid,
    default_temperature double precision NOT NULL,
    default_max_tokens integer NOT NULL,
    icon character varying(10) NOT NULL,
    color character varying(20) NOT NULL,
    category character varying(50) NOT NULL,
    is_builtin boolean NOT NULL,
    is_active boolean NOT NULL,
    created_by character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_default boolean DEFAULT false NOT NULL
);


--
-- Name: chat_assistants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chat_assistants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chat_assistants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chat_assistants_id_seq OWNED BY public.chat_assistants.id;


--
-- Name: chat_handoff_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_handoff_events (
    id uuid NOT NULL,
    session_id character varying(50) NOT NULL,
    user_id character varying(50) NOT NULL,
    source_agent_id character varying(50) NOT NULL,
    target_agent_id character varying(50) NOT NULL,
    reason text NOT NULL,
    handoff_summary text NOT NULL,
    user_intent text NOT NULL,
    artifacts jsonb DEFAULT '[]'::jsonb NOT NULL,
    constraints jsonb DEFAULT '[]'::jsonb NOT NULL,
    hop_index integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: chat_message_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_message_events (
    message_id character varying(50) NOT NULL,
    seq integer NOT NULL,
    event_type character varying(50) NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: chat_message_feedbacks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_message_feedbacks (
    id uuid NOT NULL,
    feedback_id character varying(50) NOT NULL,
    session_id character varying(50) NOT NULL,
    message_id character varying(50) NOT NULL,
    user_id character varying(50) NOT NULL,
    rating character varying(10) NOT NULL,
    comment text,
    context jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: chat_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_messages (
    id uuid NOT NULL,
    message_id character varying(50) NOT NULL,
    session_id character varying(50) NOT NULL,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    content_type character varying(20) NOT NULL,
    metadata_json json NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: chat_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_sessions (
    id uuid NOT NULL,
    session_id character varying(50) NOT NULL,
    user_id character varying(50) NOT NULL,
    assistant_id character varying(50),
    title character varying(200) NOT NULL,
    model_id uuid NOT NULL,
    message_count integer NOT NULL,
    total_tokens integer NOT NULL,
    status character varying(20) NOT NULL,
    last_message_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    agent_id character varying(50),
    mode character varying(16) DEFAULT 'chat'::character varying NOT NULL,
    workspace_id character varying(64),
    sandbox_meta jsonb,
    share_token_hash character varying(64),
    share_expires_at timestamp with time zone,
    shared_at timestamp with time zone,
    title_locked boolean NOT NULL,
    project_id character varying(64),
    last_settled_message_id character varying(50)
);


--
-- Name: collaboration_degradation_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collaboration_degradation_events (
    id uuid NOT NULL,
    session_id character varying(50) NOT NULL,
    message_id character varying(50),
    user_id character varying(50),
    intent character varying(20) NOT NULL,
    reason character varying(180) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: cookie_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cookie_accounts (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    balance numeric(12,2) NOT NULL,
    frozen_balance numeric(12,2) NOT NULL,
    total_earned numeric(12,2) NOT NULL,
    total_spent numeric(12,2) NOT NULL,
    total_adjusted numeric(12,2) NOT NULL,
    status character varying(20) NOT NULL,
    frozen_reason text,
    frozen_by uuid,
    frozen_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_account_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'frozen'::character varying, 'suspended'::character varying])::text[])))
);


--
-- Name: cookie_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cookie_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cookie_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cookie_accounts_id_seq OWNED BY public.cookie_accounts.id;


--
-- Name: cookie_consumption_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cookie_consumption_logs (
    id bigint NOT NULL,
    task_id character varying(100),
    sandbox_session_id character varying(100),
    user_id uuid NOT NULL,
    transaction_id bigint,
    billing_item character varying(50) NOT NULL,
    quantity numeric(10,4) NOT NULL,
    unit_price numeric(10,4) NOT NULL,
    total_cost numeric(12,2) NOT NULL,
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    duration_seconds integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_billing_item CHECK (((billing_item)::text = ANY ((ARRAY['task_base'::character varying, 'cpu_usage'::character varying, 'memory_usage'::character varying, 'execution_time'::character varying, 'sandbox_session'::character varying, 'sandbox_cpu'::character varying, 'sandbox_memory'::character varying])::text[])))
);


--
-- Name: cookie_consumption_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cookie_consumption_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cookie_consumption_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cookie_consumption_logs_id_seq OWNED BY public.cookie_consumption_logs.id;


--
-- Name: cookie_discounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cookie_discounts (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    discount_multiplier numeric(8,4) NOT NULL,
    date_start date NOT NULL,
    date_end date NOT NULL,
    daily_start time without time zone,
    daily_end time without time zone,
    timezone character varying(64) DEFAULT 'Asia/Shanghai'::character varying NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    banner_title character varying(200) NOT NULL,
    banner_description text NOT NULL,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_cookie_discount_multiplier CHECK (((discount_multiplier >= (0)::numeric) AND (discount_multiplier <= (1)::numeric)))
);


--
-- Name: cookie_discounts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cookie_discounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cookie_discounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cookie_discounts_id_seq OWNED BY public.cookie_discounts.id;


--
-- Name: cookie_ledger; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cookie_ledger (
    id bigint NOT NULL,
    snapshot_date date NOT NULL,
    user_id uuid NOT NULL,
    account_id integer NOT NULL,
    opening_balance numeric(12,2) NOT NULL,
    total_earned numeric(12,2) NOT NULL,
    total_spent numeric(12,2) NOT NULL,
    total_adjusted numeric(12,2) NOT NULL,
    closing_balance numeric(12,2) NOT NULL,
    transaction_count integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cookie_ledger_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cookie_ledger_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cookie_ledger_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cookie_ledger_id_seq OWNED BY public.cookie_ledger.id;


--
-- Name: cookie_pricing; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cookie_pricing (
    id integer NOT NULL,
    pricing_type character varying(30) NOT NULL,
    resource_type character varying(50),
    flow_category character varying(50),
    base_cost numeric(10,4) NOT NULL,
    unit character varying(20) NOT NULL,
    is_active boolean NOT NULL,
    effective_from timestamp with time zone DEFAULT now() NOT NULL,
    effective_until timestamp with time zone,
    priority integer NOT NULL,
    description text,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    per_sample_cost numeric(10,4) DEFAULT '0'::numeric,
    per_comparison_cost numeric(10,4) DEFAULT '0'::numeric,
    CONSTRAINT chk_pricing_type CHECK (((pricing_type)::text = ANY ((ARRAY['task_type'::character varying, 'resource'::character varying, 'sandbox'::character varying, 'bonus'::character varying])::text[]))),
    CONSTRAINT chk_pricing_unit CHECK (((unit)::text = ANY ((ARRAY['per_task'::character varying, 'per_hour'::character varying, 'per_core_hour'::character varying, 'per_gb_hour'::character varying, 'per_session'::character varying, 'per_user'::character varying, 'per_sample'::character varying, 'per_comparison'::character varying])::text[])))
);


--
-- Name: cookie_pricing_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cookie_pricing_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cookie_pricing_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cookie_pricing_id_seq OWNED BY public.cookie_pricing.id;


--
-- Name: cookie_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cookie_transactions (
    id bigint NOT NULL,
    account_id integer NOT NULL,
    user_id uuid NOT NULL,
    txn_type character varying(30) NOT NULL,
    amount numeric(12,2) NOT NULL,
    balance_after numeric(12,2) NOT NULL,
    source_type character varying(30),
    source_id character varying(100),
    admin_id uuid,
    adjust_reason text,
    task_type character varying(50),
    resource_cores integer,
    resource_memory_gb numeric(6,1),
    execution_seconds integer,
    description text NOT NULL,
    ip_address character varying(45),
    user_agent text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_txn_amount_sign CHECK (((((txn_type)::text <> 'earn'::text) OR (amount >= (0)::numeric)) AND (((txn_type)::text <> 'refund'::text) OR (amount >= (0)::numeric)) AND (((txn_type)::text <> 'unfreeze'::text) OR (amount >= (0)::numeric)) AND (((txn_type)::text <> ALL ((ARRAY['spend'::character varying, 'freeze'::character varying])::text[])) OR (amount <= (0)::numeric))))
);


--
-- Name: cookie_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cookie_transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cookie_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cookie_transactions_id_seq OWNED BY public.cookie_transactions.id;


--
-- Name: dataset_analysis_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dataset_analysis_links (
    id uuid NOT NULL,
    version_id uuid NOT NULL,
    task_id uuid,
    handoff_hash character varying(64) NOT NULL,
    flow_id character varying(80) NOT NULL,
    confirmation_id character varying(128),
    parameters_hash character varying(64) NOT NULL,
    normalized_request json NOT NULL,
    state character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    execution_binding json
);


--
-- Name: dataset_assets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dataset_assets (
    id uuid NOT NULL,
    version_id uuid NOT NULL,
    file_record_id uuid NOT NULL,
    download_task_id uuid,
    role character varying(40) NOT NULL,
    data_type character varying(48) NOT NULL,
    format character varying(32) NOT NULL,
    compression character varying(16) NOT NULL,
    original_name character varying(500) NOT NULL,
    storage_name character varying(500) NOT NULL,
    size bigint NOT NULL,
    sha256 character varying(64),
    checksum_status character varying(32) NOT NULL,
    availability character varying(32) NOT NULL,
    classification json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dataset_ingestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dataset_ingestions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    version_id uuid,
    request_key character varying(80) NOT NULL,
    parameters_hash character varying(64) NOT NULL,
    normalized_request json NOT NULL,
    confirmation_id character varying(128),
    invocation_id uuid,
    agent_session_id character varying(50),
    task_ids json NOT NULL,
    state character varying(32) NOT NULL,
    errors json NOT NULL,
    preview json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    approval_snapshot json
);


--
-- Name: dataset_samples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dataset_samples (
    id uuid NOT NULL,
    version_id uuid NOT NULL,
    sample_id uuid NOT NULL,
    sample_key character varying(200) NOT NULL,
    source_accessions json NOT NULL,
    file_record_ids json NOT NULL,
    source_metadata json NOT NULL,
    user_annotation json NOT NULL,
    mapping_status character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dataset_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dataset_sources (
    id uuid NOT NULL,
    version_id uuid NOT NULL,
    repository character varying(32) NOT NULL,
    accession character varying(80) NOT NULL,
    parent_accession character varying(80),
    source_url text NOT NULL,
    access_status character varying(32) NOT NULL,
    evidence json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dataset_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dataset_versions (
    id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    number integer NOT NULL,
    status character varying(32) NOT NULL,
    source_snapshot json NOT NULL,
    validation json NOT NULL,
    review_annotations json NOT NULL,
    asset_fingerprint character varying(64),
    handoff json,
    revision_reason text NOT NULL,
    initiated_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: datasets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.datasets (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    description text NOT NULL,
    assay_type character varying(40) NOT NULL,
    organism json NOT NULL,
    status character varying(32) NOT NULL,
    schema_version character varying(16) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: doc_audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doc_audit_logs (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    action character varying(32) NOT NULL,
    actor_id uuid NOT NULL,
    actor_name character varying(128) NOT NULL,
    reason character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: doc_editors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doc_editors (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    user_id uuid NOT NULL,
    user_name character varying(128) NOT NULL,
    edit_count integer DEFAULT 1 NOT NULL,
    first_edit timestamp with time zone DEFAULT now() NOT NULL,
    last_edit timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: doc_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doc_revisions (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    content text NOT NULL,
    edit_summary character varying(500),
    edited_by uuid NOT NULL,
    status integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: download_execution_admissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.download_execution_admissions (
    id uuid NOT NULL,
    budget_id uuid NOT NULL,
    ingestion_id uuid NOT NULL,
    task_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    project_id uuid NOT NULL,
    confirmation_id character varying(128) NOT NULL,
    request_digest character varying(64) NOT NULL,
    source character varying(40) NOT NULL,
    protocol character varying(20) NOT NULL,
    policy_revision character varying(128) NOT NULL,
    environment_id character varying(128) NOT NULL,
    caller_id character varying(128) NOT NULL,
    allowed_destinations json NOT NULL,
    status character varying(32) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    execution_epoch integer NOT NULL,
    revoked boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    caller_kind character varying(40) NOT NULL,
    tool_digest character varying(64) NOT NULL,
    source_digest character varying(64) NOT NULL,
    attempt_id uuid NOT NULL,
    reserved_bytes bigint NOT NULL,
    execution_id uuid,
    CONSTRAINT ck_download_admission_epoch CHECK (((execution_epoch >= 0) AND (reserved_bytes >= 0)))
);


--
-- Name: download_execution_budgets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.download_execution_budgets (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    project_id uuid,
    limit_bytes bigint NOT NULL,
    reserved_bytes bigint NOT NULL,
    admitted_bytes bigint,
    status character varying(32) NOT NULL,
    policy_revision character varying(128) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    disk_block_limit_bytes bigint NOT NULL,
    disk_inodes_limit bigint NOT NULL,
    CONSTRAINT ck_download_budget_disk CHECK (((disk_block_limit_bytes > 0) AND (disk_inodes_limit > 0))),
    CONSTRAINT ck_download_budget_measurement CHECK (((admitted_bytes IS NULL) OR ((admitted_bytes >= 0) AND (admitted_bytes <= reserved_bytes)))),
    CONSTRAINT ck_download_budget_reservation CHECK (((limit_bytes > 0) AND (reserved_bytes >= 0) AND (reserved_bytes <= limit_bytes)))
);


--
-- Name: download_execution_lease_nonces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.download_execution_lease_nonces (
    id uuid NOT NULL,
    supervisor_id character varying(128) NOT NULL,
    nonce uuid NOT NULL,
    task_id uuid NOT NULL,
    execution_epoch integer NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_download_lease_nonce_epoch CHECK ((execution_epoch > 0)),
    CONSTRAINT ck_download_lease_nonce_supervisor CHECK ((length(TRIM(BOTH FROM supervisor_id)) > 0))
);


--
-- Name: download_execution_receipt_nonces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.download_execution_receipt_nonces (
    id uuid NOT NULL,
    supervisor_id character varying(128) NOT NULL,
    nonce uuid NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: download_execution_scopes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.download_execution_scopes (
    id uuid NOT NULL,
    scope_ref uuid NOT NULL,
    admission_ref uuid NOT NULL,
    budget_ref uuid NOT NULL,
    task_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    execution_id uuid NOT NULL,
    execution_epoch integer NOT NULL,
    caller_id character varying(128) NOT NULL,
    environment_id character varying(128) NOT NULL,
    policy_revision character varying(128) NOT NULL,
    state character varying(20) NOT NULL,
    pid integer,
    started_at timestamp with time zone,
    stopped_at timestamp with time zone,
    lease_deadline timestamp with time zone NOT NULL,
    reason character varying(32) NOT NULL,
    egress_revoked boolean NOT NULL,
    cleanup_complete boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    pid_start_time character varying(32),
    host_boot_id character varying(64),
    returncode integer,
    CONSTRAINT ck_download_scope_epoch CHECK ((execution_epoch > 0)),
    CONSTRAINT ck_download_scope_state CHECK (((state)::text = ANY ((ARRAY['prepared'::character varying, 'starting'::character varying, 'running'::character varying, 'stopped'::character varying, 'unknown'::character varying])::text[])))
);


--
-- Name: festival_claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.festival_claims (
    id integer NOT NULL,
    user_id uuid NOT NULL,
    festival_id character varying(50) NOT NULL,
    year integer NOT NULL,
    amount double precision DEFAULT '0'::double precision NOT NULL,
    transaction_id integer,
    claimed_at timestamp with time zone NOT NULL
);


--
-- Name: COLUMN festival_claims.user_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.festival_claims.user_id IS '领取用户 ID';


--
-- Name: COLUMN festival_claims.festival_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.festival_claims.festival_id IS '节日标识';


--
-- Name: COLUMN festival_claims.year; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.festival_claims.year IS '领取年份';


--
-- Name: COLUMN festival_claims.amount; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.festival_claims.amount IS '领取金额';


--
-- Name: COLUMN festival_claims.transaction_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.festival_claims.transaction_id IS '关联饼干交易流水 ID';


--
-- Name: COLUMN festival_claims.claimed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.festival_claims.claimed_at IS '领取时间';


--
-- Name: festival_claims_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.festival_claims_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: festival_claims_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.festival_claims_id_seq OWNED BY public.festival_claims.id;


--
-- Name: file_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_records (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    original_name character varying(500) NOT NULL,
    storage_path character varying(1024) NOT NULL,
    size bigint DEFAULT 0 NOT NULL,
    checksum character varying(64) DEFAULT ''::character varying NOT NULL,
    file_type character varying(32) DEFAULT 'other'::character varying NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    directory character varying(500) DEFAULT ''::character varying NOT NULL,
    source character varying(32) DEFAULT 'upload'::character varying NOT NULL,
    task_id uuid,
    lifecycle_status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    cleanup_after timestamp with time zone,
    storage_backend character varying(16) DEFAULT 'local'::character varying NOT NULL,
    owner_scope character varying(20) DEFAULT 'personal'::character varying NOT NULL,
    team_id uuid
);


--
-- Name: kb_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kb_chunks (
    id bigint NOT NULL,
    document_id character varying(64) NOT NULL,
    chunk_index integer NOT NULL,
    section_path character varying(512) DEFAULT ''::character varying NOT NULL,
    content text NOT NULL,
    content_hash character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    embedding public.vector(1024),
    embedding_model character varying(120)
);


--
-- Name: kb_chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kb_chunks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kb_chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.kb_chunks_id_seq OWNED BY public.kb_chunks.id;


--
-- Name: kb_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kb_documents (
    id uuid NOT NULL,
    doc_id character varying(64) NOT NULL,
    title character varying(255) NOT NULL,
    category character varying(128) NOT NULL,
    file_path character varying(500) NOT NULL,
    status integer DEFAULT 1 NOT NULL,
    current_rev uuid,
    pending_rev uuid,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    kb_id character varying(64),
    project_id character varying(64)
);


--
-- Name: kb_issues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kb_issues (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    user_id uuid NOT NULL,
    user_name character varying(128) NOT NULL,
    content text NOT NULL,
    reply_to uuid,
    status integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: knowledge_bases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_bases (
    id character varying(64) NOT NULL,
    name character varying(128) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    show_in_lab boolean DEFAULT true NOT NULL,
    ai_searchable boolean DEFAULT true NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    project_id character varying(64)
);


--
-- Name: mas_a2a_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_a2a_events (
    event_id uuid NOT NULL,
    run_id uuid NOT NULL,
    node_id uuid,
    event_type character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    dedupe_key character varying(512) NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    published_at timestamp with time zone,
    delivery_status character varying(32) NOT NULL
);


--
-- Name: mas_approvals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_approvals (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    node_id uuid,
    kind character varying(64) NOT NULL,
    prompt text NOT NULL,
    options jsonb NOT NULL,
    response jsonb,
    status character varying(32) NOT NULL,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mas_artifacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_artifacts (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    node_id uuid,
    logical_name character varying(128) NOT NULL,
    kind character varying(32) NOT NULL,
    workspace_path character varying(1024) NOT NULL,
    media_type character varying(255) NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 character varying(64) NOT NULL,
    schema_version character varying(32) NOT NULL,
    summary jsonb NOT NULL,
    metadata jsonb NOT NULL,
    visibility character varying(32) NOT NULL,
    state character varying(32) NOT NULL,
    storage_class character varying(32) NOT NULL,
    version integer NOT NULL,
    reference_count integer NOT NULL,
    lease_expires_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    project_id character varying(64)
);


--
-- Name: mas_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_nodes (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    node_key character varying(64) NOT NULL,
    agent_id character varying(128) NOT NULL,
    intent character varying(256) NOT NULL,
    depends_on jsonb NOT NULL,
    input_contract jsonb NOT NULL,
    output_contract jsonb NOT NULL,
    parameters jsonb NOT NULL,
    resources jsonb NOT NULL,
    status character varying(32) NOT NULL,
    attempt_count integer NOT NULL,
    max_attempts integer NOT NULL,
    idempotency_key character varying(256) NOT NULL,
    version integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mas_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_plans (
    id uuid NOT NULL,
    run_id uuid,
    schema_version character varying(32) NOT NULL,
    plan_json jsonb NOT NULL,
    plan_hash character varying(64) NOT NULL,
    validated_at timestamp with time zone,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mas_rework_guards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_rework_guards (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    target_node_id uuid NOT NULL,
    input_artifact_id uuid NOT NULL,
    input_sha256 character varying(64) NOT NULL,
    error_code character varying(128) NOT NULL,
    remediation_kind character varying(128) NOT NULL,
    fingerprint character varying(64) NOT NULL,
    attempt_count integer NOT NULL,
    status character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mas_room_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_room_events (
    event_id uuid NOT NULL,
    run_id character varying(64) NOT NULL,
    sequence integer NOT NULL,
    event_type character varying(96) NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    occurred_at timestamp with time zone DEFAULT now()
);


--
-- Name: mas_room_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_room_messages (
    id uuid NOT NULL,
    room_id character varying(64) NOT NULL,
    run_id character varying(64),
    agent_id character varying(128),
    role character varying(32) NOT NULL,
    content text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mas_room_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_room_runs (
    run_id character varying(64) NOT NULL,
    room_id character varying(64) NOT NULL,
    user_id character varying(50) NOT NULL,
    status character varying(48) DEFAULT 'running'::character varying NOT NULL,
    root_request text NOT NULL,
    orchestration_rounds integer DEFAULT 0 NOT NULL,
    pending_plan jsonb,
    plan_decision jsonb,
    error text,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: mas_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mas_runs (
    id uuid NOT NULL,
    session_id uuid,
    user_id uuid NOT NULL,
    workspace_id uuid,
    plan_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    context_summary jsonb NOT NULL,
    version integer NOT NULL,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    project_id character varying(64)
);


--
-- Name: mcp_builds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcp_builds (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    requirement text NOT NULL,
    plan_summary text DEFAULT ''::text NOT NULL,
    search_queries json DEFAULT '[]'::json NOT NULL,
    search_results json DEFAULT '[]'::json NOT NULL,
    generated_code text DEFAULT ''::text NOT NULL,
    runtime character varying(20) DEFAULT 'python'::character varying NOT NULL,
    safety_report json,
    mcp_server_id uuid,
    version character varying(20) DEFAULT '1.0.0'::character varying NOT NULL,
    parent_build_id uuid,
    status character varying(30) DEFAULT 'planning'::character varying NOT NULL,
    test_cases json DEFAULT '[]'::json NOT NULL,
    test_passed boolean,
    build_doc text DEFAULT ''::text NOT NULL,
    architecture_doc text DEFAULT ''::text NOT NULL,
    model_used character varying(50) DEFAULT ''::character varying NOT NULL,
    tokens_consumed integer,
    generation_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mcp_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcp_logs (
    id integer NOT NULL,
    service_id uuid NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    level character varying(20) NOT NULL,
    message text NOT NULL,
    source character varying(100) DEFAULT 'internal'::character varying NOT NULL
);


--
-- Name: mcp_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mcp_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mcp_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mcp_logs_id_seq OWNED BY public.mcp_logs.id;


--
-- Name: mcp_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcp_reviews (
    id uuid NOT NULL,
    build_id uuid NOT NULL,
    reviewer_id uuid NOT NULL,
    decision character varying(20),
    comment text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mcp_servers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcp_servers (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    description text NOT NULL,
    transport character varying(20) NOT NULL,
    command character varying(500) NOT NULL,
    url character varying(500) NOT NULL,
    env json NOT NULL,
    status character varying(20) NOT NULL,
    tools json NOT NULL,
    timeout integer NOT NULL,
    auto_restart boolean NOT NULL,
    is_preset boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    args json DEFAULT '[]'::json NOT NULL,
    registry character varying(50) DEFAULT 'default'::character varying NOT NULL,
    working_dir character varying(500) DEFAULT ''::character varying NOT NULL,
    version character varying(20) DEFAULT ''::character varying NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    pool character varying(20) DEFAULT 'production'::character varying NOT NULL,
    expires_at timestamp with time zone,
    created_by uuid,
    current_version character varying(20) DEFAULT '1.0.0'::character varying NOT NULL,
    generation_meta json DEFAULT '{}'::json NOT NULL,
    review_status character varying(20) DEFAULT 'approved'::character varying NOT NULL,
    is_template boolean DEFAULT false NOT NULL
);


--
-- Name: mcp_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcp_versions (
    id uuid NOT NULL,
    mcp_server_id uuid NOT NULL,
    build_id uuid,
    version character varying(20) NOT NULL,
    version_tag character varying(50) DEFAULT ''::character varying NOT NULL,
    is_major boolean DEFAULT false NOT NULL,
    code_snapshot text DEFAULT ''::text NOT NULL,
    tools_snapshot json,
    changelog text DEFAULT ''::text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    config_snapshot json,
    source character varying(20) DEFAULT 'builder'::character varying NOT NULL,
    contract_digest character varying(80) DEFAULT ''::character varying NOT NULL
);


--
-- Name: mcp_visibility; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mcp_visibility (
    id uuid NOT NULL,
    mcp_server_id uuid NOT NULL,
    user_id uuid NOT NULL,
    access_level character varying(20) DEFAULT 'read'::character varying NOT NULL,
    granted_by uuid,
    granted_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone
);


--
-- Name: memory_blocks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_blocks (
    id integer NOT NULL,
    user_id character varying(50) NOT NULL,
    agent_id character varying(50) NOT NULL,
    block_name character varying(32) NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    char_limit integer DEFAULT 2000 NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: memory_blocks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memory_blocks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_blocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memory_blocks_id_seq OWNED BY public.memory_blocks.id;


--
-- Name: memory_facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_facts (
    id integer NOT NULL,
    user_id character varying(50) NOT NULL,
    agent_id character varying(50) NOT NULL,
    scope character varying(16) NOT NULL,
    content character varying(300) NOT NULL,
    content_hash character varying(64) NOT NULL,
    keywords jsonb,
    embedding public.vector(1024),
    embedding_model character varying(120),
    source_session_id character varying(50),
    source_message_ids jsonb,
    confidence double precision DEFAULT '0.8'::double precision NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    superseded_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_recalled_at timestamp with time zone
);


--
-- Name: memory_facts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memory_facts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_facts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memory_facts_id_seq OWNED BY public.memory_facts.id;


--
-- Name: memory_settlements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_settlements (
    id integer NOT NULL,
    range_key character varying(180) NOT NULL,
    session_id character varying(50) NOT NULL,
    start_message_id character varying(50),
    end_message_id character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: memory_settlements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memory_settlements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_settlements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memory_settlements_id_seq OWNED BY public.memory_settlements.id;


--
-- Name: model_routing_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_routing_decisions (
    id uuid NOT NULL,
    request_id character varying(64) NOT NULL,
    step_index integer DEFAULT 0 NOT NULL,
    agent_id character varying(64) NOT NULL,
    complexity character varying(16),
    explicit_model_id character varying(64),
    model_tier character varying(16),
    chosen_provider character varying(64) NOT NULL,
    cascade_providers jsonb DEFAULT '[]'::jsonb NOT NULL,
    candidates_considered jsonb DEFAULT '[]'::jsonb NOT NULL,
    decision_reason character varying(64) NOT NULL,
    cascade_events jsonb DEFAULT '[]'::jsonb NOT NULL,
    degraded boolean DEFAULT false NOT NULL,
    degrade_reason character varying(64),
    usage_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid NOT NULL,
    title character varying(200) NOT NULL,
    content text NOT NULL,
    level character varying(20) NOT NULL,
    created_by uuid NOT NULL,
    is_global boolean NOT NULL,
    target_user_id uuid,
    read_by jsonb NOT NULL,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    type character varying(64) DEFAULT 'general'::character varying NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: overdrive_commands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.overdrive_commands (
    command_id character varying(128) NOT NULL,
    run_id character varying(64) NOT NULL,
    command_type character varying(64) NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    result jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: overdrive_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.overdrive_events (
    event_id uuid NOT NULL,
    run_id character varying(64) NOT NULL,
    sequence integer NOT NULL,
    event_type character varying(96) NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    dedupe_key character varying(256),
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: overdrive_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.overdrive_runs (
    run_id character varying(64) NOT NULL,
    session_id character varying(50) NOT NULL,
    user_id character varying(50) NOT NULL,
    status character varying(48) NOT NULL,
    root_request text NOT NULL,
    lead_planner_agent_id character varying(128),
    research jsonb DEFAULT '{}'::jsonb NOT NULL,
    plan jsonb DEFAULT '{}'::jsonb NOT NULL,
    manager_tasks jsonb DEFAULT '[]'::jsonb NOT NULL,
    tasks jsonb DEFAULT '[]'::jsonb NOT NULL,
    assistant_instances jsonb DEFAULT '[]'::jsonb NOT NULL,
    manager_reviews jsonb DEFAULT '[]'::jsonb NOT NULL,
    artifact_index jsonb DEFAULT '[]'::jsonb NOT NULL,
    control jsonb DEFAULT '{}'::jsonb NOT NULL,
    event_cursor integer DEFAULT 0 NOT NULL,
    version integer DEFAULT 0 NOT NULL,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: overdrive_task_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.overdrive_task_results (
    id uuid NOT NULL,
    run_id character varying(64) NOT NULL,
    task_id character varying(128) NOT NULL,
    attempt integer NOT NULL,
    status character varying(48) NOT NULL,
    result jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: platform_run_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_run_events (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid,
    project_slug character varying(200) NOT NULL,
    executor character varying(64) DEFAULT 'snakemake'::character varying NOT NULL,
    status character varying(32) NOT NULL,
    phase character varying(64) DEFAULT 'task'::character varying NOT NULL,
    progress double precision DEFAULT '0'::double precision NOT NULL,
    rule character varying(255),
    payload jsonb NOT NULL,
    sequence integer NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    published_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: platform_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_runs (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_slug character varying(200) NOT NULL,
    flow_id character varying(100) NOT NULL,
    release_id character varying(64) NOT NULL,
    request_key character varying(128) NOT NULL,
    plan_json jsonb NOT NULL,
    plan_digest character varying(64) NOT NULL,
    status character varying(32) DEFAULT 'draft'::character varying NOT NULL,
    task_id uuid,
    confirmed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: project_export_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_export_jobs (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    request_key character varying(36) NOT NULL,
    manifest_digest character varying(64) NOT NULL,
    manifest json NOT NULL,
    status character varying(20) NOT NULL,
    attempt_count integer NOT NULL,
    retryable boolean NOT NULL,
    error_code character varying(64),
    archive_path character varying(1024),
    archive_sha256 character varying(64),
    archive_size integer,
    file_record_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_export_status CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'collecting'::character varying, 'validating'::character varying, 'packaging'::character varying, 'verifying'::character varying, 'publishing'::character varying, 'ready'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: project_export_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_export_requests (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    request_key character varying(36) NOT NULL,
    job_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: project_report_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_report_jobs (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    source_manifest_job_id uuid NOT NULL,
    request_key character varying(36) NOT NULL,
    source_digest character varying(64) NOT NULL,
    source_snapshot json NOT NULL,
    parent_id uuid,
    version integer NOT NULL,
    status character varying(20) NOT NULL,
    attempt_count integer NOT NULL,
    retryable boolean DEFAULT false NOT NULL,
    error_code character varying(64),
    archive_path character varying(1024),
    html_file_record_id uuid,
    html_sha256 character varying(64),
    html_size integer,
    pdf_file_record_id uuid,
    pdf_sha256 character varying(64),
    pdf_size integer,
    pdf_status character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_report_counters CHECK (((version >= 1) AND (attempt_count >= 0))),
    CONSTRAINT ck_project_report_ready_file CHECK ((((status)::text <> 'ready'::text) OR ((html_file_record_id IS NOT NULL) AND (html_sha256 IS NOT NULL) AND (html_size IS NOT NULL) AND (html_size > 0)))),
    CONSTRAINT ck_project_report_status CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'validating'::character varying, 'rendering'::character varying, 'publishing'::character varying, 'ready'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: project_report_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_report_requests (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    request_key character varying(36) NOT NULL,
    job_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(200) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    customer character varying(200) DEFAULT ''::character varying NOT NULL,
    status character varying(20),
    settings jsonb
);


--
-- Name: qc_verification_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.qc_verification_checks (
    id uuid NOT NULL,
    case_id character varying(80) NOT NULL,
    claim_hash character varying(64) NOT NULL,
    verdict character varying(16) NOT NULL,
    evidence_event_id character varying(128),
    reviewer_agent character varying(80) NOT NULL,
    claim_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    reason character varying(1000) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: reminder_deliveries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reminder_deliveries (
    id uuid NOT NULL,
    schedule_id uuid NOT NULL,
    occurrence_id uuid NOT NULL,
    user_id uuid NOT NULL,
    channel character varying(20) DEFAULT 'in_app'::character varying NOT NULL,
    reminder_offset_minutes integer DEFAULT 0 NOT NULL,
    due_at timestamp with time zone NOT NULL,
    sent_at timestamp with time zone,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    next_retry_at timestamp with time zone,
    provider_message_id character varying(200),
    last_error text,
    notification_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: report_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_files (
    id uuid NOT NULL,
    report_id uuid,
    name character varying(200) NOT NULL,
    type character varying(20) NOT NULL,
    size integer DEFAULT 0 NOT NULL,
    path character varying(500) DEFAULT ''::character varying NOT NULL,
    is_primary boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sha256 character varying(64),
    file_record_id uuid,
    project_report_job_id uuid,
    CONSTRAINT ck_report_files_source CHECK ((((report_id IS NOT NULL) AND (project_report_job_id IS NULL)) OR ((report_id IS NULL) AND (project_report_job_id IS NOT NULL))))
);


--
-- Name: report_generation_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_generation_jobs (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    user_id uuid NOT NULL,
    run_id uuid,
    idempotency_key character varying(128) NOT NULL,
    template_version character varying(40) NOT NULL,
    status character varying(20) NOT NULL,
    error_message text NOT NULL,
    error_code character varying(64),
    retryable boolean NOT NULL,
    evidence_partial boolean NOT NULL,
    finished_at timestamp with time zone,
    archive_path character varying(1024),
    attempt_count integer NOT NULL,
    snapshot_id uuid,
    report_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_report_generation_jobs_status CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'collecting'::character varying, 'rendering'::character varying, 'publishing'::character varying, 'ready'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: report_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_snapshots (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    user_id uuid NOT NULL,
    run_id uuid,
    schema_version character varying(80) NOT NULL,
    snapshot_digest character varying(64) NOT NULL,
    payload json NOT NULL,
    captured_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reports (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    user_id uuid NOT NULL,
    flow_id character varying(100) NOT NULL,
    flow_name character varying(100) DEFAULT ''::character varying NOT NULL,
    flow_version character varying(20) DEFAULT ''::character varying NOT NULL,
    flow_icon character varying(50) DEFAULT ''::character varying NOT NULL,
    title character varying(200) DEFAULT ''::character varying NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    status character varying(20) DEFAULT 'generating'::character varying NOT NULL,
    sample_count integer DEFAULT 0 NOT NULL,
    duration integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    is_read boolean DEFAULT false NOT NULL,
    is_starred boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    parent_id uuid,
    version integer DEFAULT 1 NOT NULL,
    report_kind character varying(32) DEFAULT 'scientific'::character varying NOT NULL,
    snapshot_id uuid,
    template_version character varying(40),
    evidence_partial boolean,
    result_observation_id uuid
);


--
-- Name: research_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.research_plans (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    series_id uuid NOT NULL,
    version integer NOT NULL,
    request_key character varying(80) NOT NULL,
    draft json NOT NULL,
    digest character varying(64) NOT NULL,
    status character varying(40) NOT NULL,
    steps json NOT NULL,
    gaps json NOT NULL,
    events json NOT NULL,
    reviewed_at timestamp with time zone,
    superseded_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: result_manifest_observations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.result_manifest_observations (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    analysis_link_id uuid NOT NULL,
    task_id uuid NOT NULL,
    evidence_digest character varying(64) NOT NULL,
    manifest_sha256 character varying(64),
    payload json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: samples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.samples (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    species character varying(100) DEFAULT ''::character varying NOT NULL,
    tissue character varying(100) DEFAULT ''::character varying NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    metadata json DEFAULT '{}'::json NOT NULL,
    file_ids json DEFAULT '[]'::json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sandbox_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sandbox_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    container_id character varying(100),
    container_name character varying(128) NOT NULL,
    status character varying(20) NOT NULL,
    language character varying(20) NOT NULL,
    last_activity timestamp with time zone NOT NULL,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: schedule_occurrences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schedule_occurrences (
    id uuid NOT NULL,
    schedule_id uuid NOT NULL,
    occurrence_key character varying(64) NOT NULL,
    scheduled_at timestamp with time zone NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    fired_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schedules (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    workspace_id uuid,
    team_id uuid,
    title character varying(200) NOT NULL,
    description text,
    timezone character varying(50) DEFAULT 'Asia/Shanghai'::character varying NOT NULL,
    start_at timestamp with time zone NOT NULL,
    end_at timestamp with time zone,
    duration_seconds integer DEFAULT 0 NOT NULL,
    recurrence_rule character varying(500),
    next_fire_at timestamp with time zone,
    last_fired_at timestamp with time zone,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    source character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    metadata_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: search_provider_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_provider_configs (
    id character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    provider_type character varying(20) NOT NULL,
    api_key text DEFAULT ''::text NOT NULL,
    base_url character varying(500) DEFAULT ''::character varying NOT NULL,
    is_enabled boolean DEFAULT false NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    params jsonb DEFAULT '{}'::jsonb NOT NULL,
    timeout_seconds integer DEFAULT 10 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: site_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.site_settings (
    id integer NOT NULL,
    registration_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    totp_policy character varying(16) DEFAULT 'optional'::character varying NOT NULL,
    home_quick_entries json DEFAULT '[]'::json NOT NULL,
    subagent_fanout_enabled boolean DEFAULT false NOT NULL,
    agentteams_chat_entry_enabled boolean NOT NULL,
    collaboration_preset character varying(16) DEFAULT 'custom'::character varying NOT NULL,
    multi_expert_consultation_enabled boolean DEFAULT false NOT NULL,
    unified_intent_router_enabled boolean DEFAULT false NOT NULL,
    collaboration_degradation_locale character varying(8) DEFAULT 'zh-CN'::character varying NOT NULL,
    collaboration_degradation_template_zh character varying(1000) DEFAULT ''::character varying NOT NULL,
    collaboration_degradation_template_en character varying(1000) DEFAULT ''::character varying NOT NULL,
    agent_memory_enabled boolean DEFAULT true NOT NULL
);


--
-- Name: site_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.site_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: site_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.site_settings_id_seq OWNED BY public.site_settings.id;


--
-- Name: skill_invocations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skill_invocations (
    id uuid NOT NULL,
    skill_id character varying(100),
    skill_name character varying(100) DEFAULT ''::character varying NOT NULL,
    skill_version character varying(50),
    source character varying(20) DEFAULT ''::character varying NOT NULL,
    tool_name character varying(50) DEFAULT 'use_skill'::character varying NOT NULL,
    status character varying(20) DEFAULT 'completed'::character varying NOT NULL,
    duration_ms double precision,
    summary text DEFAULT ''::text NOT NULL,
    error text DEFAULT ''::text NOT NULL,
    session_id uuid,
    message_id uuid,
    user_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: skill_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skill_versions (
    id uuid NOT NULL,
    skill_id character varying(100) NOT NULL,
    revision integer NOT NULL,
    version character varying(50),
    name character varying(100) DEFAULT ''::character varying NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    prompt text DEFAULT ''::text NOT NULL,
    tool_definition json,
    icon character varying(10) DEFAULT ''::character varying NOT NULL,
    category character varying(50) DEFAULT ''::character varying NOT NULL,
    frontmatter json,
    source character varying(20) DEFAULT 'admin'::character varying NOT NULL,
    changelog text DEFAULT ''::text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skills (
    id uuid NOT NULL,
    skill_id character varying(100) NOT NULL,
    name character varying(100) NOT NULL,
    description text NOT NULL,
    prompt text NOT NULL,
    tool_definition json,
    icon character varying(10) NOT NULL,
    category character varying(50) NOT NULL,
    is_active boolean NOT NULL,
    is_builtin boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    version character varying(50),
    author character varying(100),
    source_type character varying(20) DEFAULT 'json'::character varying NOT NULL,
    source_ref character varying(500),
    source_commit character varying(64),
    has_scripts boolean DEFAULT false NOT NULL,
    frontmatter json
);


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tasks (
    id uuid NOT NULL,
    flow_id character varying(100) NOT NULL,
    user_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    status character varying(20) NOT NULL,
    execution_mode character varying(20) NOT NULL,
    parameters json NOT NULL,
    work_dir character varying(500) NOT NULL,
    result_path character varying(500) NOT NULL,
    error_message text NOT NULL,
    progress double precision NOT NULL,
    logs json NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sample_count integer DEFAULT 0 NOT NULL,
    idempotency_key character varying(128)
);


--
-- Name: team_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.team_members (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role character varying(20) DEFAULT 'reader'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teams (
    id uuid NOT NULL,
    name character varying(200) NOT NULL,
    owner_id uuid NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: terminal_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.terminal_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    session_id character varying(32) NOT NULL,
    container_id character varying(100),
    host_port integer,
    status character varying(20) DEFAULT 'creating'::character varying NOT NULL,
    last_activity timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    image_id character varying(32)
);


--
-- Name: upload_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.upload_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    file_name character varying(500) NOT NULL,
    total_size bigint NOT NULL,
    chunk_size bigint NOT NULL,
    total_chunks integer NOT NULL,
    uploaded_chunks json DEFAULT '[]'::json NOT NULL,
    file_md5 character varying(64),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    directory character varying(500) DEFAULT ''::character varying NOT NULL
);


--
-- Name: user_agent_capabilities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_agent_capabilities (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    agent_id character varying(50) NOT NULL,
    model_id uuid,
    mcp_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    skill_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    features jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_directories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_directories (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    path character varying(500) NOT NULL,
    name character varying(200) NOT NULL,
    parent_path character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_system boolean DEFAULT false NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    username character varying(100) NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password text NOT NULL,
    role character varying(20) NOT NULL,
    status character varying(20) NOT NULL,
    workspace_id uuid,
    avatar_url character varying(500),
    preferences json NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    storage_quota bigint DEFAULT '536870912000'::bigint NOT NULL,
    used_storage bigint DEFAULT 0 NOT NULL,
    admin_note text,
    lab_group character varying(120),
    nickname character varying(120),
    totp_secret character varying(255),
    is_2fa_enabled boolean DEFAULT false NOT NULL,
    token_version integer DEFAULT 0 NOT NULL,
    disabled_modules json DEFAULT '[]'::json NOT NULL
);


--
-- Name: workspace_archives; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspace_archives (
    id uuid NOT NULL,
    session_id character varying(50) NOT NULL,
    user_id character varying(50) NOT NULL,
    package_path character varying(1024) NOT NULL,
    size_bytes bigint NOT NULL,
    manifest_sha256 character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    restored_at timestamp with time zone,
    deleted_at timestamp with time zone
);


--
-- Name: workspaces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workspaces (
    id uuid NOT NULL,
    owner_id uuid NOT NULL,
    name character varying(200) NOT NULL,
    storage_quota integer NOT NULL,
    used_storage integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agentteams_bridge_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_bridge_settings ALTER COLUMN id SET DEFAULT nextval('public.agentteams_bridge_settings_id_seq'::regclass);


--
-- Name: chat_assistants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_assistants ALTER COLUMN id SET DEFAULT nextval('public.chat_assistants_id_seq'::regclass);


--
-- Name: cookie_accounts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_accounts ALTER COLUMN id SET DEFAULT nextval('public.cookie_accounts_id_seq'::regclass);


--
-- Name: cookie_consumption_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_consumption_logs ALTER COLUMN id SET DEFAULT nextval('public.cookie_consumption_logs_id_seq'::regclass);


--
-- Name: cookie_discounts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_discounts ALTER COLUMN id SET DEFAULT nextval('public.cookie_discounts_id_seq'::regclass);


--
-- Name: cookie_ledger id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_ledger ALTER COLUMN id SET DEFAULT nextval('public.cookie_ledger_id_seq'::regclass);


--
-- Name: cookie_pricing id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_pricing ALTER COLUMN id SET DEFAULT nextval('public.cookie_pricing_id_seq'::regclass);


--
-- Name: cookie_transactions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_transactions ALTER COLUMN id SET DEFAULT nextval('public.cookie_transactions_id_seq'::regclass);


--
-- Name: festival_claims id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.festival_claims ALTER COLUMN id SET DEFAULT nextval('public.festival_claims_id_seq'::regclass);


--
-- Name: kb_chunks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_chunks ALTER COLUMN id SET DEFAULT nextval('public.kb_chunks_id_seq'::regclass);


--
-- Name: mcp_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_logs ALTER COLUMN id SET DEFAULT nextval('public.mcp_logs_id_seq'::regclass);


--
-- Name: memory_blocks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_blocks ALTER COLUMN id SET DEFAULT nextval('public.memory_blocks_id_seq'::regclass);


--
-- Name: memory_facts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts ALTER COLUMN id SET DEFAULT nextval('public.memory_facts_id_seq'::regclass);


--
-- Name: memory_settlements id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_settlements ALTER COLUMN id SET DEFAULT nextval('public.memory_settlements_id_seq'::regclass);


--
-- Name: site_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.site_settings ALTER COLUMN id SET DEFAULT nextval('public.site_settings_id_seq'::regclass);


--
-- Name: agent_goal_events agent_goal_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goal_events
    ADD CONSTRAINT agent_goal_events_pkey PRIMARY KEY (id);


--
-- Name: agent_goal_work_units agent_goal_work_units_idempotency_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goal_work_units
    ADD CONSTRAINT agent_goal_work_units_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: agent_goal_work_units agent_goal_work_units_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goal_work_units
    ADD CONSTRAINT agent_goal_work_units_pkey PRIMARY KEY (id);


--
-- Name: agent_goals agent_goals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goals
    ADD CONSTRAINT agent_goals_pkey PRIMARY KEY (id);


--
-- Name: agent_memories agent_memories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_memories
    ADD CONSTRAINT agent_memories_pkey PRIMARY KEY (id);


--
-- Name: agent_templates agent_templates_agent_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_templates
    ADD CONSTRAINT agent_templates_agent_id_key UNIQUE (agent_id);


--
-- Name: agent_templates agent_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_templates
    ADD CONSTRAINT agent_templates_pkey PRIMARY KEY (id);


--
-- Name: agent_tool_invocations agent_tool_invocations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tool_invocations
    ADD CONSTRAINT agent_tool_invocations_pkey PRIMARY KEY (id);


--
-- Name: agentteams_bridge_settings agentteams_bridge_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_bridge_settings
    ADD CONSTRAINT agentteams_bridge_settings_pkey PRIMARY KEY (id);


--
-- Name: agentteams_case_cursors agentteams_case_cursors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_case_cursors
    ADD CONSTRAINT agentteams_case_cursors_pkey PRIMARY KEY (id);


--
-- Name: agentteams_room_members agentteams_room_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_room_members
    ADD CONSTRAINT agentteams_room_members_pkey PRIMARY KEY (id);


--
-- Name: agentteams_rooms agentteams_rooms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_rooms
    ADD CONSTRAINT agentteams_rooms_pkey PRIMARY KEY (id);


--
-- Name: agentteams_turn_records agentteams_turn_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_turn_records
    ADD CONSTRAINT agentteams_turn_records_pkey PRIMARY KEY (record_id);


--
-- Name: agentteams_turn_records agentteams_turn_records_s3_uri_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_turn_records
    ADD CONSTRAINT agentteams_turn_records_s3_uri_key UNIQUE (s3_uri);


--
-- Name: ai_call_metrics ai_call_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_call_metrics
    ADD CONSTRAINT ai_call_metrics_pkey PRIMARY KEY (id);


--
-- Name: ai_conversations ai_conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_conversations
    ADD CONSTRAINT ai_conversations_pkey PRIMARY KEY (id);


--
-- Name: ai_messages ai_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_messages
    ADD CONSTRAINT ai_messages_pkey PRIMARY KEY (id);


--
-- Name: ai_metric_alerts ai_metric_alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_metric_alerts
    ADD CONSTRAINT ai_metric_alerts_pkey PRIMARY KEY (id);


--
-- Name: ai_provider_configs ai_provider_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_provider_configs
    ADD CONSTRAINT ai_provider_configs_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: announcements announcements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_pkey PRIMARY KEY (id);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: blast_databases blast_databases_db_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blast_databases
    ADD CONSTRAINT blast_databases_db_key_key UNIQUE (db_key);


--
-- Name: blast_databases blast_databases_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blast_databases
    ADD CONSTRAINT blast_databases_name_key UNIQUE (name);


--
-- Name: blast_databases blast_databases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blast_databases
    ADD CONSTRAINT blast_databases_pkey PRIMARY KEY (id);


--
-- Name: blast_tasks blast_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blast_tasks
    ADD CONSTRAINT blast_tasks_pkey PRIMARY KEY (id);


--
-- Name: blast_tasks blast_tasks_task_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blast_tasks
    ADD CONSTRAINT blast_tasks_task_id_key UNIQUE (task_id);


--
-- Name: case_artifact_dependencies case_artifact_dependencies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.case_artifact_dependencies
    ADD CONSTRAINT case_artifact_dependencies_pkey PRIMARY KEY (id);


--
-- Name: case_artifact_versions case_artifact_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.case_artifact_versions
    ADD CONSTRAINT case_artifact_versions_pkey PRIMARY KEY (id);


--
-- Name: chat_assistants chat_assistants_assistant_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_assistants
    ADD CONSTRAINT chat_assistants_assistant_id_key UNIQUE (assistant_id);


--
-- Name: chat_assistants chat_assistants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_assistants
    ADD CONSTRAINT chat_assistants_pkey PRIMARY KEY (id);


--
-- Name: chat_handoff_events chat_handoff_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_handoff_events
    ADD CONSTRAINT chat_handoff_events_pkey PRIMARY KEY (id);


--
-- Name: chat_message_feedbacks chat_message_feedbacks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_message_feedbacks
    ADD CONSTRAINT chat_message_feedbacks_pkey PRIMARY KEY (id);


--
-- Name: chat_messages chat_messages_message_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_message_id_key UNIQUE (message_id);


--
-- Name: chat_messages chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_pkey PRIMARY KEY (id);


--
-- Name: chat_sessions chat_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_pkey PRIMARY KEY (id);


--
-- Name: chat_sessions chat_sessions_session_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_session_id_key UNIQUE (session_id);


--
-- Name: collaboration_degradation_events collaboration_degradation_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collaboration_degradation_events
    ADD CONSTRAINT collaboration_degradation_events_pkey PRIMARY KEY (id);


--
-- Name: cookie_accounts cookie_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_accounts
    ADD CONSTRAINT cookie_accounts_pkey PRIMARY KEY (id);


--
-- Name: cookie_accounts cookie_accounts_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_accounts
    ADD CONSTRAINT cookie_accounts_user_id_key UNIQUE (user_id);


--
-- Name: cookie_consumption_logs cookie_consumption_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_consumption_logs
    ADD CONSTRAINT cookie_consumption_logs_pkey PRIMARY KEY (id);


--
-- Name: cookie_discounts cookie_discounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_discounts
    ADD CONSTRAINT cookie_discounts_pkey PRIMARY KEY (id);


--
-- Name: cookie_ledger cookie_ledger_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_ledger
    ADD CONSTRAINT cookie_ledger_pkey PRIMARY KEY (id);


--
-- Name: cookie_pricing cookie_pricing_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_pricing
    ADD CONSTRAINT cookie_pricing_pkey PRIMARY KEY (id);


--
-- Name: cookie_transactions cookie_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_transactions
    ADD CONSTRAINT cookie_transactions_pkey PRIMARY KEY (id);


--
-- Name: dataset_analysis_links dataset_analysis_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_analysis_links
    ADD CONSTRAINT dataset_analysis_links_pkey PRIMARY KEY (id);


--
-- Name: dataset_assets dataset_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_assets
    ADD CONSTRAINT dataset_assets_pkey PRIMARY KEY (id);


--
-- Name: dataset_ingestions dataset_ingestions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_ingestions
    ADD CONSTRAINT dataset_ingestions_pkey PRIMARY KEY (id);


--
-- Name: dataset_samples dataset_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_samples
    ADD CONSTRAINT dataset_samples_pkey PRIMARY KEY (id);


--
-- Name: dataset_sources dataset_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_sources
    ADD CONSTRAINT dataset_sources_pkey PRIMARY KEY (id);


--
-- Name: dataset_versions dataset_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_versions
    ADD CONSTRAINT dataset_versions_pkey PRIMARY KEY (id);


--
-- Name: datasets datasets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.datasets
    ADD CONSTRAINT datasets_pkey PRIMARY KEY (id);


--
-- Name: doc_audit_logs doc_audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_audit_logs
    ADD CONSTRAINT doc_audit_logs_pkey PRIMARY KEY (id);


--
-- Name: doc_editors doc_editors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_editors
    ADD CONSTRAINT doc_editors_pkey PRIMARY KEY (id);


--
-- Name: doc_revisions doc_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_revisions
    ADD CONSTRAINT doc_revisions_pkey PRIMARY KEY (id);


--
-- Name: download_execution_admissions download_execution_admissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT download_execution_admissions_pkey PRIMARY KEY (id);


--
-- Name: download_execution_budgets download_execution_budgets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_budgets
    ADD CONSTRAINT download_execution_budgets_pkey PRIMARY KEY (id);


--
-- Name: download_execution_lease_nonces download_execution_lease_nonces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_lease_nonces
    ADD CONSTRAINT download_execution_lease_nonces_pkey PRIMARY KEY (id);


--
-- Name: download_execution_receipt_nonces download_execution_receipt_nonces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_receipt_nonces
    ADD CONSTRAINT download_execution_receipt_nonces_pkey PRIMARY KEY (id);


--
-- Name: download_execution_scopes download_execution_scopes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_scopes
    ADD CONSTRAINT download_execution_scopes_pkey PRIMARY KEY (id);


--
-- Name: festival_claims festival_claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.festival_claims
    ADD CONSTRAINT festival_claims_pkey PRIMARY KEY (id);


--
-- Name: file_records file_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_records
    ADD CONSTRAINT file_records_pkey PRIMARY KEY (id);


--
-- Name: kb_documents kb_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_documents
    ADD CONSTRAINT kb_documents_pkey PRIMARY KEY (id);


--
-- Name: kb_issues kb_issues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_issues
    ADD CONSTRAINT kb_issues_pkey PRIMARY KEY (id);


--
-- Name: knowledge_bases knowledge_bases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_bases
    ADD CONSTRAINT knowledge_bases_pkey PRIMARY KEY (id);


--
-- Name: mas_a2a_events mas_a2a_events_dedupe_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_a2a_events
    ADD CONSTRAINT mas_a2a_events_dedupe_key_key UNIQUE (dedupe_key);


--
-- Name: mas_a2a_events mas_a2a_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_a2a_events
    ADD CONSTRAINT mas_a2a_events_pkey PRIMARY KEY (event_id);


--
-- Name: mas_approvals mas_approvals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_approvals
    ADD CONSTRAINT mas_approvals_pkey PRIMARY KEY (id);


--
-- Name: mas_artifacts mas_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_artifacts
    ADD CONSTRAINT mas_artifacts_pkey PRIMARY KEY (id);


--
-- Name: mas_nodes mas_nodes_idempotency_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_nodes
    ADD CONSTRAINT mas_nodes_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: mas_nodes mas_nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_nodes
    ADD CONSTRAINT mas_nodes_pkey PRIMARY KEY (id);


--
-- Name: mas_plans mas_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_plans
    ADD CONSTRAINT mas_plans_pkey PRIMARY KEY (id);


--
-- Name: mas_plans mas_plans_plan_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_plans
    ADD CONSTRAINT mas_plans_plan_hash_key UNIQUE (plan_hash);


--
-- Name: mas_rework_guards mas_rework_guards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_rework_guards
    ADD CONSTRAINT mas_rework_guards_pkey PRIMARY KEY (id);


--
-- Name: mas_room_events mas_room_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_room_events
    ADD CONSTRAINT mas_room_events_pkey PRIMARY KEY (event_id);


--
-- Name: mas_room_messages mas_room_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_room_messages
    ADD CONSTRAINT mas_room_messages_pkey PRIMARY KEY (id);


--
-- Name: mas_room_runs mas_room_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_room_runs
    ADD CONSTRAINT mas_room_runs_pkey PRIMARY KEY (run_id);


--
-- Name: mas_runs mas_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_runs
    ADD CONSTRAINT mas_runs_pkey PRIMARY KEY (id);


--
-- Name: mas_runs mas_runs_plan_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_runs
    ADD CONSTRAINT mas_runs_plan_id_key UNIQUE (plan_id);


--
-- Name: mcp_builds mcp_builds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_builds
    ADD CONSTRAINT mcp_builds_pkey PRIMARY KEY (id);


--
-- Name: mcp_logs mcp_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_logs
    ADD CONSTRAINT mcp_logs_pkey PRIMARY KEY (id);


--
-- Name: mcp_reviews mcp_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_reviews
    ADD CONSTRAINT mcp_reviews_pkey PRIMARY KEY (id);


--
-- Name: mcp_servers mcp_servers_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_servers
    ADD CONSTRAINT mcp_servers_name_key UNIQUE (name);


--
-- Name: mcp_servers mcp_servers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_servers
    ADD CONSTRAINT mcp_servers_pkey PRIMARY KEY (id);


--
-- Name: mcp_versions mcp_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_versions
    ADD CONSTRAINT mcp_versions_pkey PRIMARY KEY (id);


--
-- Name: mcp_visibility mcp_visibility_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_visibility
    ADD CONSTRAINT mcp_visibility_pkey PRIMARY KEY (id);


--
-- Name: memory_blocks memory_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_blocks
    ADD CONSTRAINT memory_blocks_pkey PRIMARY KEY (id);


--
-- Name: memory_facts memory_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT memory_facts_pkey PRIMARY KEY (id);


--
-- Name: memory_settlements memory_settlements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_settlements
    ADD CONSTRAINT memory_settlements_pkey PRIMARY KEY (id);


--
-- Name: model_routing_decisions model_routing_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_routing_decisions
    ADD CONSTRAINT model_routing_decisions_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: overdrive_commands overdrive_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_commands
    ADD CONSTRAINT overdrive_commands_pkey PRIMARY KEY (command_id);


--
-- Name: overdrive_events overdrive_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_events
    ADD CONSTRAINT overdrive_events_pkey PRIMARY KEY (event_id);


--
-- Name: overdrive_runs overdrive_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_runs
    ADD CONSTRAINT overdrive_runs_pkey PRIMARY KEY (run_id);


--
-- Name: overdrive_task_results overdrive_task_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_task_results
    ADD CONSTRAINT overdrive_task_results_pkey PRIMARY KEY (id);


--
-- Name: chat_message_events pk_chat_message_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_message_events
    ADD CONSTRAINT pk_chat_message_events PRIMARY KEY (message_id, seq);


--
-- Name: kb_chunks pk_kb_chunks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_chunks
    ADD CONSTRAINT pk_kb_chunks PRIMARY KEY (id);


--
-- Name: platform_run_events platform_run_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_run_events
    ADD CONSTRAINT platform_run_events_pkey PRIMARY KEY (id);


--
-- Name: platform_runs platform_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_runs
    ADD CONSTRAINT platform_runs_pkey PRIMARY KEY (id);


--
-- Name: platform_runs platform_runs_task_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_runs
    ADD CONSTRAINT platform_runs_task_id_key UNIQUE (task_id);


--
-- Name: project_export_jobs project_export_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_jobs
    ADD CONSTRAINT project_export_jobs_pkey PRIMARY KEY (id);


--
-- Name: project_export_requests project_export_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_requests
    ADD CONSTRAINT project_export_requests_pkey PRIMARY KEY (id);


--
-- Name: project_report_jobs project_report_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT project_report_jobs_pkey PRIMARY KEY (id);


--
-- Name: project_report_requests project_report_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_requests
    ADD CONSTRAINT project_report_requests_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: qc_verification_checks qc_verification_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qc_verification_checks
    ADD CONSTRAINT qc_verification_checks_pkey PRIMARY KEY (id);


--
-- Name: reminder_deliveries reminder_deliveries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reminder_deliveries
    ADD CONSTRAINT reminder_deliveries_pkey PRIMARY KEY (id);


--
-- Name: report_files report_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_files
    ADD CONSTRAINT report_files_pkey PRIMARY KEY (id);


--
-- Name: report_generation_jobs report_generation_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_generation_jobs
    ADD CONSTRAINT report_generation_jobs_pkey PRIMARY KEY (id);


--
-- Name: report_snapshots report_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_snapshots
    ADD CONSTRAINT report_snapshots_pkey PRIMARY KEY (id);


--
-- Name: reports reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_pkey PRIMARY KEY (id);


--
-- Name: research_plans research_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_plans
    ADD CONSTRAINT research_plans_pkey PRIMARY KEY (id);


--
-- Name: result_manifest_observations result_manifest_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.result_manifest_observations
    ADD CONSTRAINT result_manifest_observations_pkey PRIMARY KEY (id);


--
-- Name: samples samples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.samples
    ADD CONSTRAINT samples_pkey PRIMARY KEY (id);


--
-- Name: sandbox_sessions sandbox_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sandbox_sessions
    ADD CONSTRAINT sandbox_sessions_pkey PRIMARY KEY (id);


--
-- Name: schedule_occurrences schedule_occurrences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedule_occurrences
    ADD CONSTRAINT schedule_occurrences_pkey PRIMARY KEY (id);


--
-- Name: schedules schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_pkey PRIMARY KEY (id);


--
-- Name: search_provider_configs search_provider_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_provider_configs
    ADD CONSTRAINT search_provider_configs_pkey PRIMARY KEY (id);


--
-- Name: site_settings site_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.site_settings
    ADD CONSTRAINT site_settings_pkey PRIMARY KEY (id);


--
-- Name: skill_invocations skill_invocations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_invocations
    ADD CONSTRAINT skill_invocations_pkey PRIMARY KEY (id);


--
-- Name: skill_versions skill_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_versions
    ADD CONSTRAINT skill_versions_pkey PRIMARY KEY (id);


--
-- Name: skills skills_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skills
    ADD CONSTRAINT skills_pkey PRIMARY KEY (id);


--
-- Name: skills skills_skill_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skills
    ADD CONSTRAINT skills_skill_id_key UNIQUE (skill_id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: team_members team_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_pkey PRIMARY KEY (id);


--
-- Name: teams teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (id);


--
-- Name: terminal_sessions terminal_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.terminal_sessions
    ADD CONSTRAINT terminal_sessions_pkey PRIMARY KEY (id);


--
-- Name: doc_editors uk_doc_editors_document_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_editors
    ADD CONSTRAINT uk_doc_editors_document_user UNIQUE (document_id, user_id);


--
-- Name: upload_sessions upload_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_sessions
    ADD CONSTRAINT upload_sessions_pkey PRIMARY KEY (id);


--
-- Name: agentteams_case_cursors uq_agentteams_case_cursors_session_case; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_case_cursors
    ADD CONSTRAINT uq_agentteams_case_cursors_session_case UNIQUE (session_id, case_id);


--
-- Name: agentteams_room_members uq_agentteams_room_members_room_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_room_members
    ADD CONSTRAINT uq_agentteams_room_members_room_user UNIQUE (room_id, user_id);


--
-- Name: agentteams_rooms uq_agentteams_rooms_room_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_rooms
    ADD CONSTRAINT uq_agentteams_rooms_room_id UNIQUE (room_id);


--
-- Name: agentteams_turn_records uq_agentteams_turn_records_call; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_turn_records
    ADD CONSTRAINT uq_agentteams_turn_records_call UNIQUE (case_id, work_item_id, round_number, call_seq);


--
-- Name: case_artifact_dependencies uq_case_artifact_dependencies_edge; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.case_artifact_dependencies
    ADD CONSTRAINT uq_case_artifact_dependencies_edge UNIQUE (case_id, downstream_artifact_id, upstream_artifact_id, relation);


--
-- Name: case_artifact_versions uq_case_artifact_versions_case_artifact_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.case_artifact_versions
    ADD CONSTRAINT uq_case_artifact_versions_case_artifact_version UNIQUE (case_id, artifact_id, version_no);


--
-- Name: dataset_analysis_links uq_dataset_analysis_task; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_analysis_links
    ADD CONSTRAINT uq_dataset_analysis_task UNIQUE (task_id);


--
-- Name: dataset_assets uq_dataset_asset_file; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_assets
    ADD CONSTRAINT uq_dataset_asset_file UNIQUE (version_id, file_record_id);


--
-- Name: dataset_ingestions uq_dataset_import_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_ingestions
    ADD CONSTRAINT uq_dataset_import_request UNIQUE (user_id, project_id, request_key);


--
-- Name: dataset_samples uq_dataset_sample_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_samples
    ADD CONSTRAINT uq_dataset_sample_key UNIQUE (version_id, sample_key);


--
-- Name: dataset_versions uq_dataset_version_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_versions
    ADD CONSTRAINT uq_dataset_version_number UNIQUE (dataset_id, number);


--
-- Name: download_execution_admissions uq_download_admission_attempt; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT uq_download_admission_attempt UNIQUE (task_id, attempt_id, execution_epoch);


--
-- Name: download_execution_admissions uq_download_admission_execution_identity; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT uq_download_admission_execution_identity UNIQUE (task_id, execution_id);


--
-- Name: download_execution_admissions uq_download_execution_admission_ingestion; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT uq_download_execution_admission_ingestion UNIQUE (ingestion_id);


--
-- Name: download_execution_admissions uq_download_execution_admission_task; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT uq_download_execution_admission_task UNIQUE (task_id);


--
-- Name: download_execution_lease_nonces uq_download_execution_lease_nonce; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_lease_nonces
    ADD CONSTRAINT uq_download_execution_lease_nonce UNIQUE (supervisor_id, nonce);


--
-- Name: download_execution_receipt_nonces uq_download_execution_receipt_nonce; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_receipt_nonces
    ADD CONSTRAINT uq_download_execution_receipt_nonce UNIQUE (supervisor_id, nonce);


--
-- Name: download_execution_scopes uq_download_scope_execution; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_scopes
    ADD CONSTRAINT uq_download_scope_execution UNIQUE (task_id, execution_id);


--
-- Name: download_execution_scopes uq_download_scope_ref; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_scopes
    ADD CONSTRAINT uq_download_scope_ref UNIQUE (scope_ref);


--
-- Name: festival_claims uq_festival_claim_user_festival_year; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.festival_claims
    ADD CONSTRAINT uq_festival_claim_user_festival_year UNIQUE (user_id, festival_id, year);


--
-- Name: agent_goal_events uq_goal_events_goal_dedupe_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goal_events
    ADD CONSTRAINT uq_goal_events_goal_dedupe_key UNIQUE (goal_id, dedupe_key);


--
-- Name: agent_goal_events uq_goal_events_goal_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goal_events
    ADD CONSTRAINT uq_goal_events_goal_sequence UNIQUE (goal_id, sequence);


--
-- Name: agent_goal_work_units uq_goal_work_units_goal_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goal_work_units
    ADD CONSTRAINT uq_goal_work_units_goal_key UNIQUE (goal_id, work_unit_key);


--
-- Name: kb_chunks uq_kb_chunks_doc_index; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_chunks
    ADD CONSTRAINT uq_kb_chunks_doc_index UNIQUE (document_id, chunk_index);


--
-- Name: kb_documents uq_kb_documents_doc_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_documents
    ADD CONSTRAINT uq_kb_documents_doc_id UNIQUE (doc_id);


--
-- Name: mas_artifacts uq_mas_artifacts_run_name_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_artifacts
    ADD CONSTRAINT uq_mas_artifacts_run_name_version UNIQUE (run_id, logical_name, version);


--
-- Name: mas_nodes uq_mas_nodes_run_node_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_nodes
    ADD CONSTRAINT uq_mas_nodes_run_node_key UNIQUE (run_id, node_key);


--
-- Name: mas_rework_guards uq_mas_rework_guards_fingerprint; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_rework_guards
    ADD CONSTRAINT uq_mas_rework_guards_fingerprint UNIQUE (run_id, target_node_id, fingerprint);


--
-- Name: mcp_versions uq_mcp_versions_server_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_versions
    ADD CONSTRAINT uq_mcp_versions_server_version UNIQUE (mcp_server_id, version);


--
-- Name: mcp_visibility uq_mcp_visibility_server_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_visibility
    ADD CONSTRAINT uq_mcp_visibility_server_user UNIQUE (mcp_server_id, user_id);


--
-- Name: memory_blocks uq_memory_blocks_owner_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_blocks
    ADD CONSTRAINT uq_memory_blocks_owner_name UNIQUE (user_id, agent_id, block_name);


--
-- Name: memory_facts uq_memory_facts_content; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT uq_memory_facts_content UNIQUE (user_id, agent_id, content_hash);


--
-- Name: memory_settlements uq_memory_settlements_range_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_settlements
    ADD CONSTRAINT uq_memory_settlements_range_key UNIQUE (range_key);


--
-- Name: overdrive_events uq_overdrive_events_run_dedupe; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_events
    ADD CONSTRAINT uq_overdrive_events_run_dedupe UNIQUE (run_id, dedupe_key);


--
-- Name: overdrive_events uq_overdrive_events_run_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_events
    ADD CONSTRAINT uq_overdrive_events_run_sequence UNIQUE (run_id, sequence);


--
-- Name: overdrive_task_results uq_overdrive_task_results_attempt; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_task_results
    ADD CONSTRAINT uq_overdrive_task_results_attempt UNIQUE (run_id, task_id, attempt);


--
-- Name: platform_run_events uq_platform_run_event_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_run_events
    ADD CONSTRAINT uq_platform_run_event_sequence UNIQUE (run_id, sequence);


--
-- Name: platform_runs uq_platform_runs_user_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_runs
    ADD CONSTRAINT uq_platform_runs_user_request UNIQUE (user_id, request_key);


--
-- Name: project_export_jobs uq_project_export_manifest; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_jobs
    ADD CONSTRAINT uq_project_export_manifest UNIQUE (user_id, project_id, manifest_digest);


--
-- Name: project_export_jobs uq_project_export_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_jobs
    ADD CONSTRAINT uq_project_export_request UNIQUE (user_id, project_id, request_key);


--
-- Name: project_export_requests uq_project_export_request_alias; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_requests
    ADD CONSTRAINT uq_project_export_request_alias UNIQUE (user_id, project_id, request_key);


--
-- Name: project_report_requests uq_project_report_alias; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_requests
    ADD CONSTRAINT uq_project_report_alias UNIQUE (user_id, project_id, request_key);


--
-- Name: project_report_jobs uq_project_report_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT uq_project_report_request UNIQUE (user_id, project_id, request_key);


--
-- Name: project_report_jobs uq_project_report_source; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT uq_project_report_source UNIQUE (user_id, project_id, source_digest);


--
-- Name: projects uq_projects_user_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT uq_projects_user_slug UNIQUE (user_id, slug);


--
-- Name: reminder_deliveries uq_reminder_delivery; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reminder_deliveries
    ADD CONSTRAINT uq_reminder_delivery UNIQUE (occurrence_id, channel, reminder_offset_minutes);


--
-- Name: research_plans uq_research_plan_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_plans
    ADD CONSTRAINT uq_research_plan_request UNIQUE (user_id, project_id, request_key);


--
-- Name: research_plans uq_research_plan_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_plans
    ADD CONSTRAINT uq_research_plan_version UNIQUE (series_id, version);


--
-- Name: result_manifest_observations uq_result_observation_facts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.result_manifest_observations
    ADD CONSTRAINT uq_result_observation_facts UNIQUE (task_id, evidence_digest);


--
-- Name: schedule_occurrences uq_schedule_occurrences_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedule_occurrences
    ADD CONSTRAINT uq_schedule_occurrences_key UNIQUE (schedule_id, occurrence_key);


--
-- Name: skill_versions uq_skill_versions_skill_revision; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_versions
    ADD CONSTRAINT uq_skill_versions_skill_revision UNIQUE (skill_id, revision);


--
-- Name: team_members uq_team_members_team_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT uq_team_members_team_user UNIQUE (team_id, user_id);


--
-- Name: user_agent_capabilities uq_user_agent_capabilities_user_agent; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_agent_capabilities
    ADD CONSTRAINT uq_user_agent_capabilities_user_agent UNIQUE (user_id, agent_id);


--
-- Name: user_directories uq_user_directories_user_path; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_directories
    ADD CONSTRAINT uq_user_directories_user_path UNIQUE (user_id, path);


--
-- Name: user_agent_capabilities user_agent_capabilities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_agent_capabilities
    ADD CONSTRAINT user_agent_capabilities_pkey PRIMARY KEY (id);


--
-- Name: user_directories user_directories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_directories
    ADD CONSTRAINT user_directories_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: workspace_archives workspace_archives_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspace_archives
    ADD CONSTRAINT workspace_archives_pkey PRIMARY KEY (id);


--
-- Name: workspaces workspaces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (id);


--
-- Name: idx_accounts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_accounts_status ON public.cookie_accounts USING btree (status) WHERE ((status)::text <> 'active'::text);


--
-- Name: idx_accounts_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_accounts_updated_at ON public.cookie_accounts USING btree (updated_at);


--
-- Name: idx_agent_memories_project_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_memories_project_status ON public.agent_memories USING btree (project_id, status);


--
-- Name: idx_agent_memories_user_agent_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_memories_user_agent_status ON public.agent_memories USING btree (user_id, agent_id, status);


--
-- Name: idx_agent_memories_user_scope_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_memories_user_scope_status ON public.agent_memories USING btree (user_id, scope, status);


--
-- Name: idx_agent_templates_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_templates_category ON public.agent_templates USING btree (category, is_active);


--
-- Name: idx_agentteams_room_members_user_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agentteams_room_members_user_status ON public.agentteams_room_members USING btree (user_id, status);


--
-- Name: idx_agentteams_rooms_owner_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agentteams_rooms_owner_updated ON public.agentteams_rooms USING btree (owner_id, updated_at);


--
-- Name: idx_agentteams_turn_records_case_work_round; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agentteams_turn_records_case_work_round ON public.agentteams_turn_records USING btree (case_id, work_item_id, round_number);


--
-- Name: idx_ai_conv_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_conv_user ON public.ai_conversations USING btree (user_id, updated_at);


--
-- Name: idx_ai_msg_conv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_msg_conv ON public.ai_messages USING btree (conversation_id, "timestamp");


--
-- Name: idx_chat_feedbacks_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_feedbacks_created ON public.chat_message_feedbacks USING btree (created_at);


--
-- Name: idx_chat_feedbacks_message_user; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_chat_feedbacks_message_user ON public.chat_message_feedbacks USING btree (message_id, user_id);


--
-- Name: idx_chat_handoff_session_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_handoff_session_created ON public.chat_handoff_events USING btree (session_id, created_at);


--
-- Name: idx_chat_messages_session_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_messages_session_created ON public.chat_messages USING btree (session_id, created_at);


--
-- Name: idx_chat_sessions_user_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_sessions_user_updated ON public.chat_sessions USING btree (user_id, updated_at);


--
-- Name: idx_collab_degradation_intent_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_collab_degradation_intent_created ON public.collaboration_degradation_events USING btree (intent, created_at);


--
-- Name: idx_collab_degradation_session_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_collab_degradation_session_created ON public.collaboration_degradation_events USING btree (session_id, created_at);


--
-- Name: idx_cookie_discount_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cookie_discount_active ON public.cookie_discounts USING btree (is_active, date_start, date_end);


--
-- Name: idx_deliveries_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deliveries_due ON public.reminder_deliveries USING btree (due_at, status);


--
-- Name: idx_deliveries_retry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deliveries_retry ON public.reminder_deliveries USING btree (next_retry_at, status, attempt_count);


--
-- Name: idx_deliveries_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deliveries_user ON public.reminder_deliveries USING btree (user_id, status, created_at);


--
-- Name: idx_festival_claim_festival; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_festival_claim_festival ON public.festival_claims USING btree (festival_id, year);


--
-- Name: idx_festival_claim_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_festival_claim_user ON public.festival_claims USING btree (user_id, claimed_at);


--
-- Name: idx_ledger_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ledger_date ON public.cookie_ledger USING btree (snapshot_date);


--
-- Name: idx_ledger_user_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ledger_user_date ON public.cookie_ledger USING btree (user_id, snapshot_date);


--
-- Name: idx_logs_sandbox; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_logs_sandbox ON public.cookie_consumption_logs USING btree (sandbox_session_id) WHERE (sandbox_session_id IS NOT NULL);


--
-- Name: idx_logs_task; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_logs_task ON public.cookie_consumption_logs USING btree (task_id) WHERE (task_id IS NOT NULL);


--
-- Name: idx_logs_transaction; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_logs_transaction ON public.cookie_consumption_logs USING btree (transaction_id);


--
-- Name: idx_logs_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_logs_user_created ON public.cookie_consumption_logs USING btree (user_id, created_at);


--
-- Name: idx_mcp_builds_server; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_builds_server ON public.mcp_builds USING btree (mcp_server_id);


--
-- Name: idx_mcp_builds_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_builds_status ON public.mcp_builds USING btree (status);


--
-- Name: idx_mcp_builds_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_builds_user ON public.mcp_builds USING btree (user_id);


--
-- Name: idx_mcp_logs_service_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_logs_service_timestamp ON public.mcp_logs USING btree (service_id, "timestamp");


--
-- Name: idx_mcp_reviews_build; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_reviews_build ON public.mcp_reviews USING btree (build_id);


--
-- Name: idx_mcp_servers_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_servers_expires_at ON public.mcp_servers USING btree (expires_at);


--
-- Name: idx_mcp_servers_pool; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_servers_pool ON public.mcp_servers USING btree (pool);


--
-- Name: idx_mcp_versions_server; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_versions_server ON public.mcp_versions USING btree (mcp_server_id);


--
-- Name: idx_mcp_visibility_server; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_visibility_server ON public.mcp_visibility USING btree (mcp_server_id);


--
-- Name: idx_mcp_visibility_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mcp_visibility_user ON public.mcp_visibility USING btree (user_id);


--
-- Name: idx_memory_blocks_user_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memory_blocks_user_agent ON public.memory_blocks USING btree (user_id, agent_id);


--
-- Name: idx_memory_facts_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memory_facts_embedding_hnsw ON public.memory_facts USING hnsw (embedding public.vector_cosine_ops) WHERE (embedding IS NOT NULL);


--
-- Name: idx_memory_facts_user_agent_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memory_facts_user_agent_status ON public.memory_facts USING btree (user_id, agent_id, status);


--
-- Name: idx_mrd_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mrd_created ON public.model_routing_decisions USING btree (created_at);


--
-- Name: idx_mrd_request; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_mrd_request ON public.model_routing_decisions USING btree (request_id, step_index);


--
-- Name: idx_occurrences_schedule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_occurrences_schedule ON public.schedule_occurrences USING btree (schedule_id, scheduled_at);


--
-- Name: idx_pricing_effective; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pricing_effective ON public.cookie_pricing USING btree (effective_from, effective_until);


--
-- Name: idx_pricing_query; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pricing_query ON public.cookie_pricing USING btree (flow_category, resource_type, priority) WHERE (is_active = true);


--
-- Name: idx_schedules_next_fire; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedules_next_fire ON public.schedules USING btree (next_fire_at, status);


--
-- Name: idx_schedules_user_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedules_user_status ON public.schedules USING btree (user_id, status);


--
-- Name: idx_schedules_workspace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedules_workspace ON public.schedules USING btree (workspace_id, status);


--
-- Name: idx_txn_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_txn_account ON public.cookie_transactions USING btree (account_id, created_at);


--
-- Name: idx_txn_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_txn_source ON public.cookie_transactions USING btree (source_type, source_id) WHERE (source_id IS NOT NULL);


--
-- Name: idx_txn_type_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_txn_type_created ON public.cookie_transactions USING btree (txn_type, created_at);


--
-- Name: idx_txn_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_txn_user_created ON public.cookie_transactions USING btree (user_id, created_at, txn_type);


--
-- Name: idx_user_agent_capabilities_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_agent_capabilities_agent ON public.user_agent_capabilities USING btree (agent_id);


--
-- Name: idx_workspace_archives_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_archives_expires_at ON public.workspace_archives USING btree (expires_at);


--
-- Name: idx_workspace_archives_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_archives_session_id ON public.workspace_archives USING btree (session_id);


--
-- Name: idx_workspace_archives_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_archives_user_created ON public.workspace_archives USING btree (user_id, created_at);


--
-- Name: idx_workspace_archives_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workspace_archives_user_id ON public.workspace_archives USING btree (user_id);


--
-- Name: ix_agent_goal_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goal_events_event_type ON public.agent_goal_events USING btree (event_type);


--
-- Name: ix_agent_goal_events_goal_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goal_events_goal_id ON public.agent_goal_events USING btree (goal_id);


--
-- Name: ix_agent_goal_work_units_goal_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goal_work_units_goal_id ON public.agent_goal_work_units USING btree (goal_id);


--
-- Name: ix_agent_goal_work_units_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goal_work_units_status ON public.agent_goal_work_units USING btree (status);


--
-- Name: ix_agent_goals_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goals_session_id ON public.agent_goals USING btree (session_id);


--
-- Name: ix_agent_goals_session_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goals_session_status ON public.agent_goals USING btree (session_id, status);


--
-- Name: ix_agent_goals_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goals_status ON public.agent_goals USING btree (status);


--
-- Name: ix_agent_goals_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goals_user_id ON public.agent_goals USING btree (user_id);


--
-- Name: ix_agent_goals_user_status_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goals_user_status_updated ON public.agent_goals USING btree (user_id, status, updated_at);


--
-- Name: ix_agent_goals_workspace_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_goals_workspace_id ON public.agent_goals USING btree (workspace_id);


--
-- Name: ix_agent_memories_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_memories_agent_id ON public.agent_memories USING btree (agent_id);


--
-- Name: ix_agent_memories_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_memories_embedding_hnsw ON public.agent_memories USING hnsw (embedding public.vector_cosine_ops) WHERE (embedding IS NOT NULL);


--
-- Name: ix_agent_memories_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_memories_project_id ON public.agent_memories USING btree (project_id);


--
-- Name: ix_agent_memories_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_memories_scope ON public.agent_memories USING btree (scope);


--
-- Name: ix_agent_memories_source_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_memories_source_session ON public.agent_memories USING btree (source_session);


--
-- Name: ix_agent_memories_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_memories_status ON public.agent_memories USING btree (status);


--
-- Name: ix_agent_memories_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_memories_user_id ON public.agent_memories USING btree (user_id);


--
-- Name: ix_agent_templates_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_agent_templates_agent_id ON public.agent_templates USING btree (agent_id);


--
-- Name: ix_agent_templates_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_templates_project_id ON public.agent_templates USING btree (project_id);


--
-- Name: ix_agent_tool_invocations_owner_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_tool_invocations_owner_project ON public.agent_tool_invocations USING btree (owner_id, project_id);


--
-- Name: ix_agent_tool_invocations_owner_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_tool_invocations_owner_session ON public.agent_tool_invocations USING btree (owner_id, conversation_id);


--
-- Name: ix_agentteams_case_cursors_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_case_cursors_session_id ON public.agentteams_case_cursors USING btree (session_id);


--
-- Name: ix_agentteams_room_members_room_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_room_members_room_id ON public.agentteams_room_members USING btree (room_id);


--
-- Name: ix_agentteams_room_members_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_room_members_status ON public.agentteams_room_members USING btree (status);


--
-- Name: ix_agentteams_room_members_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_room_members_user_id ON public.agentteams_room_members USING btree (user_id);


--
-- Name: ix_agentteams_rooms_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_rooms_owner_id ON public.agentteams_rooms USING btree (owner_id);


--
-- Name: ix_agentteams_rooms_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_rooms_project_id ON public.agentteams_rooms USING btree (project_id);


--
-- Name: ix_agentteams_rooms_room_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_agentteams_rooms_room_id ON public.agentteams_rooms USING btree (room_id);


--
-- Name: ix_agentteams_turn_records_actor_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_turn_records_actor_user_id ON public.agentteams_turn_records USING btree (actor_user_id);


--
-- Name: ix_agentteams_turn_records_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_turn_records_case_id ON public.agentteams_turn_records USING btree (case_id);


--
-- Name: ix_agentteams_turn_records_recorded_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_turn_records_recorded_at ON public.agentteams_turn_records USING btree (recorded_at);


--
-- Name: ix_agentteams_turn_records_work_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agentteams_turn_records_work_item_id ON public.agentteams_turn_records USING btree (work_item_id);


--
-- Name: ix_ai_call_metrics_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_call_metrics_created_at ON public.ai_call_metrics USING btree (created_at);


--
-- Name: ix_ai_call_metrics_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_call_metrics_model ON public.ai_call_metrics USING btree (model);


--
-- Name: ix_ai_call_metrics_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_call_metrics_provider ON public.ai_call_metrics USING btree (provider);


--
-- Name: ix_ai_call_metrics_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_call_metrics_session_id ON public.ai_call_metrics USING btree (session_id);


--
-- Name: ix_ai_call_metrics_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_call_metrics_status ON public.ai_call_metrics USING btree (status);


--
-- Name: ix_ai_conversations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_conversations_user_id ON public.ai_conversations USING btree (user_id);


--
-- Name: ix_ai_messages_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_messages_conversation_id ON public.ai_messages USING btree (conversation_id);


--
-- Name: ix_ai_metric_alerts_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_metric_alerts_created_at ON public.ai_metric_alerts USING btree (created_at);


--
-- Name: ix_ai_metric_alerts_rule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_metric_alerts_rule ON public.ai_metric_alerts USING btree (rule);


--
-- Name: ix_ai_provider_configs_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_provider_configs_name ON public.ai_provider_configs USING btree (name);


--
-- Name: ix_api_keys_key_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_api_keys_key_hash ON public.api_keys USING btree (key_hash);


--
-- Name: ix_api_keys_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_keys_user_id ON public.api_keys USING btree (user_id);


--
-- Name: ix_audit_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);


--
-- Name: ix_audit_logs_method; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_method ON public.audit_logs USING btree (method);


--
-- Name: ix_audit_logs_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_path ON public.audit_logs USING btree (path);


--
-- Name: ix_audit_logs_resource_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_resource_id ON public.audit_logs USING btree (resource_id);


--
-- Name: ix_audit_logs_resource_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_resource_type ON public.audit_logs USING btree (resource_type);


--
-- Name: ix_audit_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_user_id ON public.audit_logs USING btree (user_id);


--
-- Name: ix_blast_databases_build_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_databases_build_status ON public.blast_databases USING btree (build_status);


--
-- Name: ix_blast_databases_db_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_databases_db_key ON public.blast_databases USING btree (db_key);


--
-- Name: ix_blast_databases_db_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_databases_db_type ON public.blast_databases USING btree (db_type);


--
-- Name: ix_blast_databases_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_databases_is_active ON public.blast_databases USING btree (is_active);


--
-- Name: ix_blast_databases_version_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_databases_version_group ON public.blast_databases USING btree (version_group);


--
-- Name: ix_blast_tasks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_tasks_status ON public.blast_tasks USING btree (status);


--
-- Name: ix_blast_tasks_submitted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_tasks_submitted_at ON public.blast_tasks USING btree (submitted_at);


--
-- Name: ix_blast_tasks_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_tasks_task_id ON public.blast_tasks USING btree (task_id);


--
-- Name: ix_blast_tasks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blast_tasks_user_id ON public.blast_tasks USING btree (user_id);


--
-- Name: ix_case_artifact_dependencies_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_case_artifact_dependencies_case_id ON public.case_artifact_dependencies USING btree (case_id);


--
-- Name: ix_case_artifact_dependencies_upstream; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_case_artifact_dependencies_upstream ON public.case_artifact_dependencies USING btree (case_id, upstream_artifact_id);


--
-- Name: ix_case_artifact_versions_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_case_artifact_versions_case_id ON public.case_artifact_versions USING btree (case_id);


--
-- Name: ix_case_artifact_versions_checksum; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_case_artifact_versions_checksum ON public.case_artifact_versions USING btree (checksum_sha256);


--
-- Name: ix_chat_assistants_assistant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_chat_assistants_assistant_id ON public.chat_assistants USING btree (assistant_id);


--
-- Name: ix_chat_assistants_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_assistants_category ON public.chat_assistants USING btree (category, is_active);


--
-- Name: ix_chat_handoff_events_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_handoff_events_session_id ON public.chat_handoff_events USING btree (session_id);


--
-- Name: ix_chat_handoff_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_handoff_events_user_id ON public.chat_handoff_events USING btree (user_id);


--
-- Name: ix_chat_message_feedbacks_feedback_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_chat_message_feedbacks_feedback_id ON public.chat_message_feedbacks USING btree (feedback_id);


--
-- Name: ix_chat_message_feedbacks_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_message_feedbacks_message_id ON public.chat_message_feedbacks USING btree (message_id);


--
-- Name: ix_chat_message_feedbacks_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_message_feedbacks_session_id ON public.chat_message_feedbacks USING btree (session_id);


--
-- Name: ix_chat_message_feedbacks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_message_feedbacks_user_id ON public.chat_message_feedbacks USING btree (user_id);


--
-- Name: ix_chat_messages_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_chat_messages_message_id ON public.chat_messages USING btree (message_id);


--
-- Name: ix_chat_messages_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_messages_session_id ON public.chat_messages USING btree (session_id);


--
-- Name: ix_chat_sessions_mode; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_sessions_mode ON public.chat_sessions USING btree (mode);


--
-- Name: ix_chat_sessions_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_sessions_project_id ON public.chat_sessions USING btree (project_id);


--
-- Name: ix_chat_sessions_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_chat_sessions_session_id ON public.chat_sessions USING btree (session_id);


--
-- Name: ix_chat_sessions_share_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_chat_sessions_share_token_hash ON public.chat_sessions USING btree (share_token_hash);


--
-- Name: ix_chat_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_sessions_user_id ON public.chat_sessions USING btree (user_id);


--
-- Name: ix_collaboration_degradation_events_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collaboration_degradation_events_message_id ON public.collaboration_degradation_events USING btree (message_id);


--
-- Name: ix_collaboration_degradation_events_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collaboration_degradation_events_session_id ON public.collaboration_degradation_events USING btree (session_id);


--
-- Name: ix_collaboration_degradation_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collaboration_degradation_events_user_id ON public.collaboration_degradation_events USING btree (user_id);


--
-- Name: ix_dataset_analysis_links_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dataset_analysis_links_version_id ON public.dataset_analysis_links USING btree (version_id);


--
-- Name: ix_dataset_assets_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dataset_assets_version_id ON public.dataset_assets USING btree (version_id);


--
-- Name: ix_dataset_ingestions_owner_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dataset_ingestions_owner_project ON public.dataset_ingestions USING btree (user_id, project_id);


--
-- Name: ix_dataset_samples_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dataset_samples_version_id ON public.dataset_samples USING btree (version_id);


--
-- Name: ix_dataset_sources_accession; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dataset_sources_accession ON public.dataset_sources USING btree (repository, accession);


--
-- Name: ix_dataset_sources_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dataset_sources_version_id ON public.dataset_sources USING btree (version_id);


--
-- Name: ix_dataset_versions_dataset_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dataset_versions_dataset_id ON public.dataset_versions USING btree (dataset_id);


--
-- Name: ix_datasets_owner_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_datasets_owner_project ON public.datasets USING btree (user_id, project_id);


--
-- Name: ix_doc_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_doc_audit_logs_action ON public.doc_audit_logs USING btree (action);


--
-- Name: ix_doc_audit_logs_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_doc_audit_logs_document_id ON public.doc_audit_logs USING btree (document_id);


--
-- Name: ix_doc_audit_logs_revision_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_doc_audit_logs_revision_id ON public.doc_audit_logs USING btree (revision_id);


--
-- Name: ix_doc_editors_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_doc_editors_document_id ON public.doc_editors USING btree (document_id);


--
-- Name: ix_doc_revisions_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_doc_revisions_document_id ON public.doc_revisions USING btree (document_id);


--
-- Name: ix_doc_revisions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_doc_revisions_status ON public.doc_revisions USING btree (status);


--
-- Name: ix_download_execution_admissions_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_download_execution_admissions_expiry ON public.download_execution_admissions USING btree (status, expires_at);


--
-- Name: ix_download_execution_budgets_owner_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_download_execution_budgets_owner_status ON public.download_execution_budgets USING btree (owner_id, status);


--
-- Name: ix_download_execution_lease_nonces_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_download_execution_lease_nonces_expires_at ON public.download_execution_lease_nonces USING btree (expires_at);


--
-- Name: ix_download_execution_receipt_nonces_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_download_execution_receipt_nonces_expires_at ON public.download_execution_receipt_nonces USING btree (expires_at);


--
-- Name: ix_download_execution_scopes_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_download_execution_scopes_expiry ON public.download_execution_scopes USING btree (state, lease_deadline);


--
-- Name: ix_file_records_directory; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_directory ON public.file_records USING btree (directory);


--
-- Name: ix_file_records_lifecycle_cleanup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_lifecycle_cleanup ON public.file_records USING btree (lifecycle_status, cleanup_after);


--
-- Name: ix_file_records_lifecycle_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_lifecycle_status ON public.file_records USING btree (lifecycle_status);


--
-- Name: ix_file_records_owner_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_owner_scope ON public.file_records USING btree (owner_scope);


--
-- Name: ix_file_records_owner_scope_team_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_owner_scope_team_id ON public.file_records USING btree (owner_scope, team_id);


--
-- Name: ix_file_records_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_source ON public.file_records USING btree (source);


--
-- Name: ix_file_records_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_status ON public.file_records USING btree (status);


--
-- Name: ix_file_records_storage_backend; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_storage_backend ON public.file_records USING btree (storage_backend);


--
-- Name: ix_file_records_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_task_id ON public.file_records USING btree (task_id);


--
-- Name: ix_file_records_team_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_team_id ON public.file_records USING btree (team_id);


--
-- Name: ix_file_records_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_records_user_id ON public.file_records USING btree (user_id);


--
-- Name: ix_kb_chunks_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_chunks_document_id ON public.kb_chunks USING btree (document_id);


--
-- Name: ix_kb_chunks_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_chunks_embedding_hnsw ON public.kb_chunks USING hnsw (embedding public.vector_cosine_ops) WHERE (embedding IS NOT NULL);


--
-- Name: ix_kb_documents_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_documents_category ON public.kb_documents USING btree (category);


--
-- Name: ix_kb_documents_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_documents_created_by ON public.kb_documents USING btree (created_by);


--
-- Name: ix_kb_documents_kb_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_documents_kb_id ON public.kb_documents USING btree (kb_id);


--
-- Name: ix_kb_documents_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_documents_project_id ON public.kb_documents USING btree (project_id);


--
-- Name: ix_kb_documents_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_documents_status ON public.kb_documents USING btree (status);


--
-- Name: ix_kb_issues_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_issues_document_id ON public.kb_issues USING btree (document_id);


--
-- Name: ix_kb_issues_reply_to; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kb_issues_reply_to ON public.kb_issues USING btree (reply_to);


--
-- Name: ix_knowledge_bases_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_knowledge_bases_project_id ON public.knowledge_bases USING btree (project_id);


--
-- Name: ix_mas_a2a_events_delivery_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_a2a_events_delivery_status ON public.mas_a2a_events USING btree (delivery_status);


--
-- Name: ix_mas_a2a_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_a2a_events_event_type ON public.mas_a2a_events USING btree (event_type);


--
-- Name: ix_mas_a2a_events_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_a2a_events_node_id ON public.mas_a2a_events USING btree (node_id);


--
-- Name: ix_mas_a2a_events_published_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_a2a_events_published_at ON public.mas_a2a_events USING btree (published_at);


--
-- Name: ix_mas_a2a_events_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_a2a_events_run_id ON public.mas_a2a_events USING btree (run_id);


--
-- Name: ix_mas_approvals_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_approvals_node_id ON public.mas_approvals USING btree (node_id);


--
-- Name: ix_mas_approvals_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_approvals_run_id ON public.mas_approvals USING btree (run_id);


--
-- Name: ix_mas_approvals_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_approvals_status ON public.mas_approvals USING btree (status);


--
-- Name: ix_mas_artifacts_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_artifacts_node_id ON public.mas_artifacts USING btree (node_id);


--
-- Name: ix_mas_artifacts_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_artifacts_project_id ON public.mas_artifacts USING btree (project_id);


--
-- Name: ix_mas_artifacts_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_artifacts_run_id ON public.mas_artifacts USING btree (run_id);


--
-- Name: ix_mas_artifacts_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_artifacts_sha256 ON public.mas_artifacts USING btree (sha256);


--
-- Name: ix_mas_artifacts_sha256_visibility; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_artifacts_sha256_visibility ON public.mas_artifacts USING btree (sha256, visibility);


--
-- Name: ix_mas_artifacts_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_artifacts_state ON public.mas_artifacts USING btree (state);


--
-- Name: ix_mas_nodes_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_nodes_run_id ON public.mas_nodes USING btree (run_id);


--
-- Name: ix_mas_nodes_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_nodes_status ON public.mas_nodes USING btree (status);


--
-- Name: ix_mas_plans_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_plans_created_by ON public.mas_plans USING btree (created_by);


--
-- Name: ix_mas_plans_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_plans_run_id ON public.mas_plans USING btree (run_id);


--
-- Name: ix_mas_rework_guards_input_artifact_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_rework_guards_input_artifact_id ON public.mas_rework_guards USING btree (input_artifact_id);


--
-- Name: ix_mas_rework_guards_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_rework_guards_run_id ON public.mas_rework_guards USING btree (run_id);


--
-- Name: ix_mas_rework_guards_target_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_rework_guards_target_node_id ON public.mas_rework_guards USING btree (target_node_id);


--
-- Name: ix_mas_room_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_events_event_type ON public.mas_room_events USING btree (event_type);


--
-- Name: ix_mas_room_events_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_events_run_id ON public.mas_room_events USING btree (run_id);


--
-- Name: ix_mas_room_events_run_seq; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_events_run_seq ON public.mas_room_events USING btree (run_id, sequence);


--
-- Name: ix_mas_room_messages_room_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_messages_room_created ON public.mas_room_messages USING btree (room_id, created_at);


--
-- Name: ix_mas_room_messages_room_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_messages_room_id ON public.mas_room_messages USING btree (room_id);


--
-- Name: ix_mas_room_messages_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_messages_run_id ON public.mas_room_messages USING btree (run_id);


--
-- Name: ix_mas_room_runs_room_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_runs_room_id ON public.mas_room_runs USING btree (room_id);


--
-- Name: ix_mas_room_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_runs_status ON public.mas_room_runs USING btree (status);


--
-- Name: ix_mas_room_runs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_room_runs_user_id ON public.mas_room_runs USING btree (user_id);


--
-- Name: ix_mas_runs_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_runs_project_id ON public.mas_runs USING btree (project_id);


--
-- Name: ix_mas_runs_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_runs_session_id ON public.mas_runs USING btree (session_id);


--
-- Name: ix_mas_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_runs_status ON public.mas_runs USING btree (status);


--
-- Name: ix_mas_runs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_runs_user_id ON public.mas_runs USING btree (user_id);


--
-- Name: ix_mas_runs_workspace_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mas_runs_workspace_id ON public.mas_runs USING btree (workspace_id);


--
-- Name: ix_mcp_servers_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_mcp_servers_name ON public.mcp_servers USING btree (name);


--
-- Name: ix_mcp_servers_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mcp_servers_status ON public.mcp_servers USING btree (status);


--
-- Name: ix_memory_settlements_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memory_settlements_session_id ON public.memory_settlements USING btree (session_id);


--
-- Name: ix_notifications_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_created_by ON public.notifications USING btree (created_by);


--
-- Name: ix_notifications_target_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_target_user_id ON public.notifications USING btree (target_user_id);


--
-- Name: ix_notifications_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_type ON public.notifications USING btree (type);


--
-- Name: ix_overdrive_commands_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_commands_run_id ON public.overdrive_commands USING btree (run_id);


--
-- Name: ix_overdrive_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_events_event_type ON public.overdrive_events USING btree (event_type);


--
-- Name: ix_overdrive_events_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_events_run_id ON public.overdrive_events USING btree (run_id);


--
-- Name: ix_overdrive_events_run_occurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_events_run_occurred ON public.overdrive_events USING btree (run_id, occurred_at);


--
-- Name: ix_overdrive_runs_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_runs_session_id ON public.overdrive_runs USING btree (session_id);


--
-- Name: ix_overdrive_runs_session_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_runs_session_updated ON public.overdrive_runs USING btree (session_id, updated_at);


--
-- Name: ix_overdrive_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_runs_status ON public.overdrive_runs USING btree (status);


--
-- Name: ix_overdrive_runs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_runs_user_id ON public.overdrive_runs USING btree (user_id);


--
-- Name: ix_overdrive_task_results_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_overdrive_task_results_run_id ON public.overdrive_task_results USING btree (run_id);


--
-- Name: ix_platform_run_events_published; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_run_events_published ON public.platform_run_events USING btree (published_at);


--
-- Name: ix_platform_run_events_run_occurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_run_events_run_occurred ON public.platform_run_events USING btree (run_id, occurred_at);


--
-- Name: ix_platform_run_events_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_run_events_status ON public.platform_run_events USING btree (status);


--
-- Name: ix_platform_run_events_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_run_events_task_id ON public.platform_run_events USING btree (task_id);


--
-- Name: ix_platform_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_runs_status ON public.platform_runs USING btree (status);


--
-- Name: ix_platform_runs_user_project_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_runs_user_project_created ON public.platform_runs USING btree (user_id, project_slug, created_at);


--
-- Name: ix_project_export_jobs_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_export_jobs_project_id ON public.project_export_jobs USING btree (project_id);


--
-- Name: ix_project_export_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_export_jobs_status ON public.project_export_jobs USING btree (status);


--
-- Name: ix_project_export_jobs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_export_jobs_user_id ON public.project_export_jobs USING btree (user_id);


--
-- Name: ix_project_report_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_report_jobs_status ON public.project_report_jobs USING btree (status);


--
-- Name: ix_projects_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_projects_user_id ON public.projects USING btree (user_id);


--
-- Name: ix_qc_verification_checks_case_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_qc_verification_checks_case_id ON public.qc_verification_checks USING btree (case_id);


--
-- Name: ix_qc_verification_checks_case_verdict; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_qc_verification_checks_case_verdict ON public.qc_verification_checks USING btree (case_id, verdict);


--
-- Name: ix_qc_verification_checks_claim_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_qc_verification_checks_claim_hash ON public.qc_verification_checks USING btree (claim_hash);


--
-- Name: ix_report_files_project_report_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_files_project_report_job_id ON public.report_files USING btree (project_report_job_id);


--
-- Name: ix_report_files_report_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_files_report_id ON public.report_files USING btree (report_id);


--
-- Name: ix_report_generation_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_generation_jobs_status ON public.report_generation_jobs USING btree (status);


--
-- Name: ix_report_generation_jobs_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_generation_jobs_task_id ON public.report_generation_jobs USING btree (task_id);


--
-- Name: ix_report_generation_jobs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_generation_jobs_user_id ON public.report_generation_jobs USING btree (user_id);


--
-- Name: ix_report_generation_jobs_user_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_generation_jobs_user_id_created_at ON public.report_generation_jobs USING btree (user_id, created_at);


--
-- Name: ix_report_snapshots_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_snapshots_task_id ON public.report_snapshots USING btree (task_id);


--
-- Name: ix_report_snapshots_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_snapshots_user_id ON public.report_snapshots USING btree (user_id);


--
-- Name: ix_reports_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reports_created_at ON public.reports USING btree (created_at);


--
-- Name: ix_reports_flow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reports_flow_id ON public.reports USING btree (flow_id);


--
-- Name: ix_reports_parent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reports_parent_id ON public.reports USING btree (parent_id);


--
-- Name: ix_reports_result_observation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reports_result_observation_id ON public.reports USING btree (result_observation_id);


--
-- Name: ix_reports_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reports_status ON public.reports USING btree (status);


--
-- Name: ix_reports_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reports_task_id ON public.reports USING btree (task_id);


--
-- Name: ix_reports_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reports_user_id ON public.reports USING btree (user_id);


--
-- Name: ix_research_plans_owner_project; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_research_plans_owner_project ON public.research_plans USING btree (user_id, project_id);


--
-- Name: ix_result_manifest_observations_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_result_manifest_observations_project_id ON public.result_manifest_observations USING btree (project_id);


--
-- Name: ix_result_manifest_observations_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_result_manifest_observations_task_id ON public.result_manifest_observations USING btree (task_id);


--
-- Name: ix_result_manifest_observations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_result_manifest_observations_user_id ON public.result_manifest_observations USING btree (user_id);


--
-- Name: ix_samples_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_samples_user_id ON public.samples USING btree (user_id);


--
-- Name: ix_sandbox_sessions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sandbox_sessions_status ON public.sandbox_sessions USING btree (status);


--
-- Name: ix_sandbox_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sandbox_sessions_user_id ON public.sandbox_sessions USING btree (user_id);


--
-- Name: ix_skill_invocations_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_skill_invocations_session_id ON public.skill_invocations USING btree (session_id);


--
-- Name: ix_skill_invocations_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_skill_invocations_skill_id ON public.skill_invocations USING btree (skill_id);


--
-- Name: ix_skill_invocations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_skill_invocations_user_id ON public.skill_invocations USING btree (user_id);


--
-- Name: ix_skill_versions_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_skill_versions_skill_id ON public.skill_versions USING btree (skill_id);


--
-- Name: ix_skills_category_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_skills_category_active ON public.skills USING btree (category, is_active);


--
-- Name: ix_skills_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_skills_skill_id ON public.skills USING btree (skill_id);


--
-- Name: ix_tasks_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tasks_created_at ON public.tasks USING btree (created_at);


--
-- Name: ix_tasks_flow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tasks_flow_id ON public.tasks USING btree (flow_id);


--
-- Name: ix_tasks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tasks_status ON public.tasks USING btree (status);


--
-- Name: ix_tasks_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tasks_user_id ON public.tasks USING btree (user_id);


--
-- Name: ix_tasks_user_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tasks_user_id_created_at ON public.tasks USING btree (user_id, created_at);


--
-- Name: ix_team_members_team_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_team_members_team_id ON public.team_members USING btree (team_id);


--
-- Name: ix_team_members_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_team_members_user_id ON public.team_members USING btree (user_id);


--
-- Name: ix_teams_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teams_owner_id ON public.teams USING btree (owner_id);


--
-- Name: ix_terminal_sessions_image_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_terminal_sessions_image_id ON public.terminal_sessions USING btree (image_id);


--
-- Name: ix_terminal_sessions_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_terminal_sessions_session_id ON public.terminal_sessions USING btree (session_id);


--
-- Name: ix_terminal_sessions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_terminal_sessions_status ON public.terminal_sessions USING btree (status);


--
-- Name: ix_terminal_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_terminal_sessions_user_id ON public.terminal_sessions USING btree (user_id);


--
-- Name: ix_upload_sessions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_upload_sessions_status ON public.upload_sessions USING btree (status);


--
-- Name: ix_upload_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_upload_sessions_user_id ON public.upload_sessions USING btree (user_id);


--
-- Name: ix_user_agent_capabilities_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_agent_capabilities_user_id ON public.user_agent_capabilities USING btree (user_id);


--
-- Name: ix_user_directories_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_directories_user_id ON public.user_directories USING btree (user_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_lab_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_lab_group ON public.users USING btree (lab_group);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: ix_workspaces_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workspaces_owner_id ON public.workspaces USING btree (owner_id);


--
-- Name: uq_ai_provider_configs_default; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_ai_provider_configs_default ON public.ai_provider_configs USING btree (is_default) WHERE (is_default = true);


--
-- Name: uq_chat_messages_matrix_event; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_chat_messages_matrix_event ON public.chat_messages USING btree (session_id, ((metadata_json ->> 'matrix_event_id'::text))) WHERE ((metadata_json ->> 'matrix_event_id'::text) IS NOT NULL);


--
-- Name: uq_chat_messages_research_request; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_chat_messages_research_request ON public.chat_messages USING btree (session_id, ((metadata_json ->> 'research_request_id'::text))) WHERE (((role)::text = 'user'::text) AND ((metadata_json ->> 'research_request_id'::text) IS NOT NULL));


--
-- Name: uq_report_generation_jobs_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_report_generation_jobs_active ON public.report_generation_jobs USING btree (user_id, task_id, template_version) WHERE ((status)::text = ANY ((ARRAY['queued'::character varying, 'collecting'::character varying, 'rendering'::character varying, 'publishing'::character varying])::text[]));


--
-- Name: uq_report_generation_jobs_idempotency_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_report_generation_jobs_idempotency_key ON public.report_generation_jobs USING btree (idempotency_key);


--
-- Name: uq_report_snapshots_digest; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_report_snapshots_digest ON public.report_snapshots USING btree (user_id, task_id, snapshot_digest);


--
-- Name: uq_reports_snapshot_template; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_reports_snapshot_template ON public.reports USING btree (user_id, snapshot_id, template_version);


--
-- Name: uq_tasks_idempotency_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_tasks_idempotency_key ON public.tasks USING btree (idempotency_key);


--
-- Name: uq_workspace_archives_session_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_workspace_archives_session_active ON public.workspace_archives USING btree (session_id) WHERE ((deleted_at IS NULL) AND (restored_at IS NULL));


--
-- Name: project_export_jobs project_export_scope_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_export_scope_guard BEFORE UPDATE ON public.project_export_jobs FOR EACH ROW EXECUTE FUNCTION public.cygnusx_project_export_guard();


--
-- Name: project_report_jobs project_report_publication_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_report_publication_guard BEFORE UPDATE ON public.project_report_jobs FOR EACH ROW EXECUTE FUNCTION public.cygnusx_project_report_publication_guard();


--
-- Name: project_report_jobs project_report_source_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_report_source_guard BEFORE UPDATE ON public.project_report_jobs FOR EACH ROW EXECUTE FUNCTION public.cygnusx_project_report_guard();


--
-- Name: report_snapshots report_snapshots_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER report_snapshots_immutable BEFORE UPDATE ON public.report_snapshots FOR EACH ROW EXECUTE FUNCTION public.reject_report_snapshot_update();


--
-- Name: research_plans research_plan_document_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER research_plan_document_immutable BEFORE UPDATE ON public.research_plans FOR EACH ROW EXECUTE FUNCTION public.cygnusx_research_plan_guard();


--
-- Name: result_manifest_observations result_observation_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER result_observation_immutable BEFORE DELETE OR UPDATE ON public.result_manifest_observations FOR EACH ROW EXECUTE FUNCTION public.cygnusx_reject_result_update();


--
-- Name: agent_goal_events agent_goal_events_goal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goal_events
    ADD CONSTRAINT agent_goal_events_goal_id_fkey FOREIGN KEY (goal_id) REFERENCES public.agent_goals(id) ON DELETE CASCADE;


--
-- Name: agent_goal_work_units agent_goal_work_units_goal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goal_work_units
    ADD CONSTRAINT agent_goal_work_units_goal_id_fkey FOREIGN KEY (goal_id) REFERENCES public.agent_goals(id) ON DELETE CASCADE;


--
-- Name: agent_goals agent_goals_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_goals
    ADD CONSTRAINT agent_goals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: agent_templates agent_templates_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_templates
    ADD CONSTRAINT agent_templates_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.ai_provider_configs(id);


--
-- Name: agentteams_case_cursors agentteams_case_cursors_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agentteams_case_cursors
    ADD CONSTRAINT agentteams_case_cursors_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE CASCADE;


--
-- Name: ai_conversations ai_conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_conversations
    ADD CONSTRAINT ai_conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: ai_messages ai_messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_messages
    ADD CONSTRAINT ai_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.ai_conversations(id) ON DELETE CASCADE;


--
-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: blast_databases blast_databases_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blast_databases
    ADD CONSTRAINT blast_databases_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: blast_tasks blast_tasks_db_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blast_tasks
    ADD CONSTRAINT blast_tasks_db_id_fkey FOREIGN KEY (db_id) REFERENCES public.blast_databases(id);


--
-- Name: blast_tasks blast_tasks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blast_tasks
    ADD CONSTRAINT blast_tasks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: chat_assistants chat_assistants_default_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_assistants
    ADD CONSTRAINT chat_assistants_default_model_id_fkey FOREIGN KEY (default_model_id) REFERENCES public.ai_provider_configs(id);


--
-- Name: chat_handoff_events chat_handoff_events_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_handoff_events
    ADD CONSTRAINT chat_handoff_events_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE CASCADE;


--
-- Name: chat_message_feedbacks chat_message_feedbacks_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_message_feedbacks
    ADD CONSTRAINT chat_message_feedbacks_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE CASCADE;


--
-- Name: chat_messages chat_messages_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE CASCADE;


--
-- Name: chat_sessions chat_sessions_assistant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_assistant_id_fkey FOREIGN KEY (assistant_id) REFERENCES public.chat_assistants(assistant_id);


--
-- Name: chat_sessions chat_sessions_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.ai_provider_configs(id);


--
-- Name: cookie_accounts cookie_accounts_frozen_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_accounts
    ADD CONSTRAINT cookie_accounts_frozen_by_fkey FOREIGN KEY (frozen_by) REFERENCES public.users(id);


--
-- Name: cookie_accounts cookie_accounts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_accounts
    ADD CONSTRAINT cookie_accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: cookie_consumption_logs cookie_consumption_logs_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_consumption_logs
    ADD CONSTRAINT cookie_consumption_logs_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.cookie_transactions(id);


--
-- Name: cookie_consumption_logs cookie_consumption_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_consumption_logs
    ADD CONSTRAINT cookie_consumption_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: cookie_discounts cookie_discounts_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_discounts
    ADD CONSTRAINT cookie_discounts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: cookie_discounts cookie_discounts_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_discounts
    ADD CONSTRAINT cookie_discounts_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: cookie_ledger cookie_ledger_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_ledger
    ADD CONSTRAINT cookie_ledger_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.cookie_accounts(id);


--
-- Name: cookie_ledger cookie_ledger_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_ledger
    ADD CONSTRAINT cookie_ledger_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: cookie_pricing cookie_pricing_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_pricing
    ADD CONSTRAINT cookie_pricing_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: cookie_pricing cookie_pricing_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_pricing
    ADD CONSTRAINT cookie_pricing_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: cookie_transactions cookie_transactions_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_transactions
    ADD CONSTRAINT cookie_transactions_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.cookie_accounts(id);


--
-- Name: cookie_transactions cookie_transactions_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_transactions
    ADD CONSTRAINT cookie_transactions_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.users(id);


--
-- Name: cookie_transactions cookie_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cookie_transactions
    ADD CONSTRAINT cookie_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: dataset_analysis_links dataset_analysis_links_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_analysis_links
    ADD CONSTRAINT dataset_analysis_links_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE RESTRICT;


--
-- Name: dataset_analysis_links dataset_analysis_links_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_analysis_links
    ADD CONSTRAINT dataset_analysis_links_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.dataset_versions(id) ON DELETE RESTRICT;


--
-- Name: dataset_assets dataset_assets_download_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_assets
    ADD CONSTRAINT dataset_assets_download_task_id_fkey FOREIGN KEY (download_task_id) REFERENCES public.tasks(id) ON DELETE RESTRICT;


--
-- Name: dataset_assets dataset_assets_file_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_assets
    ADD CONSTRAINT dataset_assets_file_record_id_fkey FOREIGN KEY (file_record_id) REFERENCES public.file_records(id) ON DELETE RESTRICT;


--
-- Name: dataset_assets dataset_assets_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_assets
    ADD CONSTRAINT dataset_assets_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.dataset_versions(id) ON DELETE RESTRICT;


--
-- Name: dataset_ingestions dataset_ingestions_invocation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_ingestions
    ADD CONSTRAINT dataset_ingestions_invocation_id_fkey FOREIGN KEY (invocation_id) REFERENCES public.agent_tool_invocations(id) ON DELETE RESTRICT;


--
-- Name: dataset_ingestions dataset_ingestions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_ingestions
    ADD CONSTRAINT dataset_ingestions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: dataset_ingestions dataset_ingestions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_ingestions
    ADD CONSTRAINT dataset_ingestions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: dataset_ingestions dataset_ingestions_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_ingestions
    ADD CONSTRAINT dataset_ingestions_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.dataset_versions(id) ON DELETE RESTRICT;


--
-- Name: dataset_samples dataset_samples_sample_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_samples
    ADD CONSTRAINT dataset_samples_sample_id_fkey FOREIGN KEY (sample_id) REFERENCES public.samples(id) ON DELETE RESTRICT;


--
-- Name: dataset_samples dataset_samples_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_samples
    ADD CONSTRAINT dataset_samples_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.dataset_versions(id) ON DELETE RESTRICT;


--
-- Name: dataset_sources dataset_sources_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_sources
    ADD CONSTRAINT dataset_sources_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.dataset_versions(id) ON DELETE RESTRICT;


--
-- Name: dataset_versions dataset_versions_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_versions
    ADD CONSTRAINT dataset_versions_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(id) ON DELETE RESTRICT;


--
-- Name: dataset_versions dataset_versions_initiated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dataset_versions
    ADD CONSTRAINT dataset_versions_initiated_by_fkey FOREIGN KEY (initiated_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: datasets datasets_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.datasets
    ADD CONSTRAINT datasets_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: datasets datasets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.datasets
    ADD CONSTRAINT datasets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: download_execution_admissions download_execution_admissions_budget_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT download_execution_admissions_budget_id_fkey FOREIGN KEY (budget_id) REFERENCES public.download_execution_budgets(id) ON DELETE RESTRICT;


--
-- Name: download_execution_admissions download_execution_admissions_ingestion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT download_execution_admissions_ingestion_id_fkey FOREIGN KEY (ingestion_id) REFERENCES public.dataset_ingestions(id) ON DELETE RESTRICT;


--
-- Name: download_execution_admissions download_execution_admissions_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT download_execution_admissions_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: download_execution_admissions download_execution_admissions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT download_execution_admissions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: download_execution_admissions download_execution_admissions_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_admissions
    ADD CONSTRAINT download_execution_admissions_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE RESTRICT;


--
-- Name: download_execution_budgets download_execution_budgets_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_budgets
    ADD CONSTRAINT download_execution_budgets_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: download_execution_budgets download_execution_budgets_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_budgets
    ADD CONSTRAINT download_execution_budgets_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: download_execution_scopes download_execution_scopes_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_scopes
    ADD CONSTRAINT download_execution_scopes_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: download_execution_scopes download_execution_scopes_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.download_execution_scopes
    ADD CONSTRAINT download_execution_scopes_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE RESTRICT;


--
-- Name: file_records file_records_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_records
    ADD CONSTRAINT file_records_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: file_records file_records_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_records
    ADD CONSTRAINT file_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: chat_sessions fk_chat_sessions_agent_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT fk_chat_sessions_agent_id FOREIGN KEY (agent_id) REFERENCES public.agent_templates(agent_id);


--
-- Name: doc_audit_logs fk_doc_audit_logs_actor_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_audit_logs
    ADD CONSTRAINT fk_doc_audit_logs_actor_id FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: doc_audit_logs fk_doc_audit_logs_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_audit_logs
    ADD CONSTRAINT fk_doc_audit_logs_document_id FOREIGN KEY (document_id) REFERENCES public.kb_documents(id) ON DELETE CASCADE;


--
-- Name: doc_audit_logs fk_doc_audit_logs_revision_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_audit_logs
    ADD CONSTRAINT fk_doc_audit_logs_revision_id FOREIGN KEY (revision_id) REFERENCES public.doc_revisions(id) ON DELETE CASCADE;


--
-- Name: doc_editors fk_doc_editors_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_editors
    ADD CONSTRAINT fk_doc_editors_document_id FOREIGN KEY (document_id) REFERENCES public.kb_documents(id) ON DELETE CASCADE;


--
-- Name: doc_editors fk_doc_editors_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_editors
    ADD CONSTRAINT fk_doc_editors_user_id FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: doc_revisions fk_doc_revisions_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_revisions
    ADD CONSTRAINT fk_doc_revisions_document_id FOREIGN KEY (document_id) REFERENCES public.kb_documents(id) ON DELETE CASCADE;


--
-- Name: doc_revisions fk_doc_revisions_edited_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doc_revisions
    ADD CONSTRAINT fk_doc_revisions_edited_by FOREIGN KEY (edited_by) REFERENCES public.users(id);


--
-- Name: kb_chunks fk_kb_chunks_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_chunks
    ADD CONSTRAINT fk_kb_chunks_document_id FOREIGN KEY (document_id) REFERENCES public.kb_documents(doc_id) ON DELETE CASCADE;


--
-- Name: kb_documents fk_kb_documents_created_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_documents
    ADD CONSTRAINT fk_kb_documents_created_by FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: kb_documents fk_kb_documents_current_rev; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_documents
    ADD CONSTRAINT fk_kb_documents_current_rev FOREIGN KEY (current_rev) REFERENCES public.doc_revisions(id);


--
-- Name: kb_documents fk_kb_documents_kb_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_documents
    ADD CONSTRAINT fk_kb_documents_kb_id FOREIGN KEY (kb_id) REFERENCES public.knowledge_bases(id);


--
-- Name: kb_documents fk_kb_documents_pending_rev; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_documents
    ADD CONSTRAINT fk_kb_documents_pending_rev FOREIGN KEY (pending_rev) REFERENCES public.doc_revisions(id);


--
-- Name: kb_issues fk_kb_issues_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_issues
    ADD CONSTRAINT fk_kb_issues_document_id FOREIGN KEY (document_id) REFERENCES public.kb_documents(id) ON DELETE CASCADE;


--
-- Name: kb_issues fk_kb_issues_reply_to; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_issues
    ADD CONSTRAINT fk_kb_issues_reply_to FOREIGN KEY (reply_to) REFERENCES public.kb_issues(id);


--
-- Name: kb_issues fk_kb_issues_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_issues
    ADD CONSTRAINT fk_kb_issues_user_id FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: report_files fk_report_files_file_record; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_files
    ADD CONSTRAINT fk_report_files_file_record FOREIGN KEY (file_record_id) REFERENCES public.file_records(id) ON DELETE RESTRICT;


--
-- Name: report_files fk_report_files_project_job; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_files
    ADD CONSTRAINT fk_report_files_project_job FOREIGN KEY (project_report_job_id) REFERENCES public.project_report_jobs(id) ON DELETE RESTRICT;


--
-- Name: reports fk_reports_parent_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT fk_reports_parent_id FOREIGN KEY (parent_id) REFERENCES public.reports(id) ON DELETE SET NULL;


--
-- Name: reports fk_reports_result_observation; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT fk_reports_result_observation FOREIGN KEY (result_observation_id) REFERENCES public.result_manifest_observations(id) ON DELETE RESTRICT;


--
-- Name: reports fk_reports_snapshot_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT fk_reports_snapshot_id FOREIGN KEY (snapshot_id) REFERENCES public.report_snapshots(id) ON DELETE RESTRICT;


--
-- Name: mas_a2a_events mas_a2a_events_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_a2a_events
    ADD CONSTRAINT mas_a2a_events_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.mas_runs(id) ON DELETE CASCADE;


--
-- Name: mas_approvals mas_approvals_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_approvals
    ADD CONSTRAINT mas_approvals_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.mas_runs(id) ON DELETE CASCADE;


--
-- Name: mas_artifacts mas_artifacts_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_artifacts
    ADD CONSTRAINT mas_artifacts_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.mas_runs(id) ON DELETE CASCADE;


--
-- Name: mas_nodes mas_nodes_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_nodes
    ADD CONSTRAINT mas_nodes_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.mas_runs(id) ON DELETE CASCADE;


--
-- Name: mas_rework_guards mas_rework_guards_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_rework_guards
    ADD CONSTRAINT mas_rework_guards_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.mas_runs(id) ON DELETE CASCADE;


--
-- Name: mas_room_events mas_room_events_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_room_events
    ADD CONSTRAINT mas_room_events_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.mas_room_runs(run_id) ON DELETE CASCADE;


--
-- Name: mas_runs mas_runs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mas_runs
    ADD CONSTRAINT mas_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: mcp_builds mcp_builds_mcp_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_builds
    ADD CONSTRAINT mcp_builds_mcp_server_id_fkey FOREIGN KEY (mcp_server_id) REFERENCES public.mcp_servers(id) ON DELETE SET NULL;


--
-- Name: mcp_builds mcp_builds_parent_build_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_builds
    ADD CONSTRAINT mcp_builds_parent_build_id_fkey FOREIGN KEY (parent_build_id) REFERENCES public.mcp_builds(id) ON DELETE SET NULL;


--
-- Name: mcp_logs mcp_logs_service_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_logs
    ADD CONSTRAINT mcp_logs_service_id_fkey FOREIGN KEY (service_id) REFERENCES public.mcp_servers(id) ON DELETE CASCADE;


--
-- Name: mcp_reviews mcp_reviews_build_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_reviews
    ADD CONSTRAINT mcp_reviews_build_id_fkey FOREIGN KEY (build_id) REFERENCES public.mcp_builds(id) ON DELETE CASCADE;


--
-- Name: mcp_versions mcp_versions_build_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_versions
    ADD CONSTRAINT mcp_versions_build_id_fkey FOREIGN KEY (build_id) REFERENCES public.mcp_builds(id) ON DELETE SET NULL;


--
-- Name: mcp_versions mcp_versions_mcp_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_versions
    ADD CONSTRAINT mcp_versions_mcp_server_id_fkey FOREIGN KEY (mcp_server_id) REFERENCES public.mcp_servers(id) ON DELETE CASCADE;


--
-- Name: mcp_visibility mcp_visibility_mcp_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mcp_visibility
    ADD CONSTRAINT mcp_visibility_mcp_server_id_fkey FOREIGN KEY (mcp_server_id) REFERENCES public.mcp_servers(id) ON DELETE CASCADE;


--
-- Name: memory_facts memory_facts_superseded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_facts
    ADD CONSTRAINT memory_facts_superseded_by_fkey FOREIGN KEY (superseded_by) REFERENCES public.memory_facts(id);


--
-- Name: notifications notifications_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: notifications notifications_target_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_target_user_id_fkey FOREIGN KEY (target_user_id) REFERENCES public.users(id);


--
-- Name: overdrive_commands overdrive_commands_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_commands
    ADD CONSTRAINT overdrive_commands_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.overdrive_runs(run_id) ON DELETE CASCADE;


--
-- Name: overdrive_events overdrive_events_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_events
    ADD CONSTRAINT overdrive_events_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.overdrive_runs(run_id) ON DELETE CASCADE;


--
-- Name: overdrive_runs overdrive_runs_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_runs
    ADD CONSTRAINT overdrive_runs_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id) ON DELETE CASCADE;


--
-- Name: overdrive_task_results overdrive_task_results_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.overdrive_task_results
    ADD CONSTRAINT overdrive_task_results_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.overdrive_runs(run_id) ON DELETE CASCADE;


--
-- Name: platform_run_events platform_run_events_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_run_events
    ADD CONSTRAINT platform_run_events_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.platform_runs(id) ON DELETE CASCADE;


--
-- Name: platform_runs platform_runs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_runs
    ADD CONSTRAINT platform_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: project_export_jobs project_export_jobs_file_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_jobs
    ADD CONSTRAINT project_export_jobs_file_record_id_fkey FOREIGN KEY (file_record_id) REFERENCES public.file_records(id) ON DELETE RESTRICT;


--
-- Name: project_export_jobs project_export_jobs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_jobs
    ADD CONSTRAINT project_export_jobs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: project_export_jobs project_export_jobs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_jobs
    ADD CONSTRAINT project_export_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: project_export_requests project_export_requests_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_requests
    ADD CONSTRAINT project_export_requests_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.project_export_jobs(id) ON DELETE RESTRICT;


--
-- Name: project_export_requests project_export_requests_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_requests
    ADD CONSTRAINT project_export_requests_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: project_export_requests project_export_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_export_requests
    ADD CONSTRAINT project_export_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: project_report_jobs project_report_jobs_html_file_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT project_report_jobs_html_file_record_id_fkey FOREIGN KEY (html_file_record_id) REFERENCES public.file_records(id) ON DELETE RESTRICT;


--
-- Name: project_report_jobs project_report_jobs_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT project_report_jobs_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.project_report_jobs(id) ON DELETE RESTRICT;


--
-- Name: project_report_jobs project_report_jobs_pdf_file_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT project_report_jobs_pdf_file_record_id_fkey FOREIGN KEY (pdf_file_record_id) REFERENCES public.file_records(id) ON DELETE RESTRICT;


--
-- Name: project_report_jobs project_report_jobs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT project_report_jobs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: project_report_jobs project_report_jobs_source_manifest_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT project_report_jobs_source_manifest_job_id_fkey FOREIGN KEY (source_manifest_job_id) REFERENCES public.project_export_jobs(id) ON DELETE RESTRICT;


--
-- Name: project_report_jobs project_report_jobs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_jobs
    ADD CONSTRAINT project_report_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: project_report_requests project_report_requests_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_requests
    ADD CONSTRAINT project_report_requests_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.project_report_jobs(id) ON DELETE RESTRICT;


--
-- Name: project_report_requests project_report_requests_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_requests
    ADD CONSTRAINT project_report_requests_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: project_report_requests project_report_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_report_requests
    ADD CONSTRAINT project_report_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: projects projects_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: reminder_deliveries reminder_deliveries_notification_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reminder_deliveries
    ADD CONSTRAINT reminder_deliveries_notification_id_fkey FOREIGN KEY (notification_id) REFERENCES public.notifications(id) ON DELETE SET NULL;


--
-- Name: reminder_deliveries reminder_deliveries_occurrence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reminder_deliveries
    ADD CONSTRAINT reminder_deliveries_occurrence_id_fkey FOREIGN KEY (occurrence_id) REFERENCES public.schedule_occurrences(id) ON DELETE CASCADE;


--
-- Name: reminder_deliveries reminder_deliveries_schedule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reminder_deliveries
    ADD CONSTRAINT reminder_deliveries_schedule_id_fkey FOREIGN KEY (schedule_id) REFERENCES public.schedules(id) ON DELETE CASCADE;


--
-- Name: reminder_deliveries reminder_deliveries_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reminder_deliveries
    ADD CONSTRAINT reminder_deliveries_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: report_files report_files_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_files
    ADD CONSTRAINT report_files_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id) ON DELETE CASCADE;


--
-- Name: report_generation_jobs report_generation_jobs_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_generation_jobs
    ADD CONSTRAINT report_generation_jobs_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id) ON DELETE SET NULL;


--
-- Name: report_generation_jobs report_generation_jobs_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_generation_jobs
    ADD CONSTRAINT report_generation_jobs_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.report_snapshots(id) ON DELETE SET NULL;


--
-- Name: research_plans research_plans_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_plans
    ADD CONSTRAINT research_plans_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: research_plans research_plans_superseded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_plans
    ADD CONSTRAINT research_plans_superseded_by_fkey FOREIGN KEY (superseded_by) REFERENCES public.research_plans(id) ON DELETE RESTRICT;


--
-- Name: research_plans research_plans_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_plans
    ADD CONSTRAINT research_plans_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: result_manifest_observations result_manifest_observations_analysis_link_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.result_manifest_observations
    ADD CONSTRAINT result_manifest_observations_analysis_link_id_fkey FOREIGN KEY (analysis_link_id) REFERENCES public.dataset_analysis_links(id) ON DELETE RESTRICT;


--
-- Name: result_manifest_observations result_manifest_observations_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.result_manifest_observations
    ADD CONSTRAINT result_manifest_observations_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: result_manifest_observations result_manifest_observations_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.result_manifest_observations
    ADD CONSTRAINT result_manifest_observations_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE RESTRICT;


--
-- Name: result_manifest_observations result_manifest_observations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.result_manifest_observations
    ADD CONSTRAINT result_manifest_observations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: samples samples_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.samples
    ADD CONSTRAINT samples_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: sandbox_sessions sandbox_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sandbox_sessions
    ADD CONSTRAINT sandbox_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: schedule_occurrences schedule_occurrences_schedule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedule_occurrences
    ADD CONSTRAINT schedule_occurrences_schedule_id_fkey FOREIGN KEY (schedule_id) REFERENCES public.schedules(id) ON DELETE CASCADE;


--
-- Name: schedules schedules_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: schedules schedules_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: schedules schedules_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE SET NULL;


--
-- Name: skill_versions skill_versions_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_versions
    ADD CONSTRAINT skill_versions_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(skill_id) ON DELETE CASCADE;


--
-- Name: team_members team_members_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: team_members team_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: teams teams_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: terminal_sessions terminal_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.terminal_sessions
    ADD CONSTRAINT terminal_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: upload_sessions upload_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_sessions
    ADD CONSTRAINT upload_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_agent_capabilities user_agent_capabilities_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_agent_capabilities
    ADD CONSTRAINT user_agent_capabilities_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agent_templates(agent_id) ON DELETE CASCADE;


--
-- Name: user_agent_capabilities user_agent_capabilities_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_agent_capabilities
    ADD CONSTRAINT user_agent_capabilities_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.ai_provider_configs(id);


--
-- Name: user_agent_capabilities user_agent_capabilities_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_agent_capabilities
    ADD CONSTRAINT user_agent_capabilities_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_directories user_directories_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_directories
    ADD CONSTRAINT user_directories_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: users users_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id);


--
-- PostgreSQL database dump complete
--

\unrestrict 2aEfLby7y9z4qRoBwNDbTDlUB8m6SodnNsfzVYm23cF4xiK0Kxb5UTzVYcoVIEy

