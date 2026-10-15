-- Fictional development fixtures only. No owner account, password, session, provider key, job or publishing account.
-- Safe to repeat on the same demo database: existing rows are never overwritten.
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num = '0029') THEN RAISE EXCEPTION 'Demo fixtures require Alembic revision 0029'; END IF; IF EXISTS (SELECT 1 FROM public.clients WHERE id NOT IN ('1c94477f-ed71-58c3-a3a3-c438f4bf3153','56a9ea16-4b83-5bf1-8f09-2d3817fd3407')) THEN RAISE EXCEPTION 'Demo fixtures are for an empty or existing demo database only'; END IF; END $$;
--
-- PostgreSQL database dump
--


-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: clients; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.clients (id, standard_name, short_name, industry_code, industry_name, province, city, district, address, contact_phone, contact_wechat, business_hours, service_radius, cooperation_started_on, notes, status, current_level, fact_completeness, blocking_issue_count, next_action, archived_reason, version, created_at, updated_at, normalized_name) VALUES ('1c94477f-ed71-58c3-a3a3-c438f4bf3153', '演示星光美术（虚构）', '演示星光美术（虚构）', 'art_education', '少儿美术', '演示省', '演示市', '演示区', '仅用于本地开发的虚构地址，不对应真实经营场所', NULL, NULL, NULL, NULL, '2026-10-01', '完全虚构的演示记录，请勿对外发布。', 'active', 'L0', 90, 0, '配置自己的模型并核验演示流程', NULL, 1, '2026-10-15 00:00:00+00', '2026-10-15 00:00:00+00', '演示星光美术(虚构)') ON CONFLICT DO NOTHING;
INSERT INTO public.clients (id, standard_name, short_name, industry_code, industry_name, province, city, district, address, contact_phone, contact_wechat, business_hours, service_radius, cooperation_started_on, notes, status, current_level, fact_completeness, blocking_issue_count, next_action, archived_reason, version, created_at, updated_at, normalized_name) VALUES ('56a9ea16-4b83-5bf1-8f09-2d3817fd3407', '演示安心家政（虚构）', '演示安心家政（虚构）', 'housekeeping', '家政服务', '演示省', '演示市', '演示区', '仅用于本地开发的虚构地址，不对应真实经营场所', NULL, NULL, NULL, NULL, '2026-10-01', '完全虚构的演示记录，请勿对外发布。', 'active', 'L0', 90, 0, '配置自己的模型并核验演示流程', NULL, 1, '2026-10-15 00:00:00+00', '2026-10-15 00:00:00+00', '演示安心家政(虚构)') ON CONFLICT DO NOTHING;


--
-- Data for Name: evidence; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('423a83e7-75b3-5991-b447-fabbc4f567c5', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', NULL, 'manual', '项目内置虚构演示数据', NULL, '演示星光美术（虚构）是为本地联调创建的虚构企业。', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('7281ac45-e9c4-5f7b-ab64-ec9cc9ca8b4a', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', NULL, 'manual', '项目内置虚构演示数据', NULL, '美术体验课程', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('f3811123-eb52-5a6d-a5e5-429c2887d3f2', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', NULL, 'manual', '项目内置虚构演示数据', NULL, '儿童及家长', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('df2ffce9-37ab-5c3c-8c7d-14d00b3de242', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', NULL, 'manual', '项目内置虚构演示数据', NULL, '演示区（虚构地区）', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('557c2153-00df-5218-b50b-dacdd74215e1', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', NULL, 'manual', '项目内置虚构演示数据', NULL, '小班体验与绘画材料说明', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('d083e286-caf0-525c-9eba-7723ee58c829', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', NULL, 'manual', '项目内置虚构演示数据', NULL, '不得宣称全市第一、保证效果或保证收录；不得把本演示数据当作真实经营信息。', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('63cad0d7-d499-5b65-b68a-aaf24e884d9e', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', NULL, 'manual', '项目内置虚构演示数据', NULL, '演示安心家政（虚构）是为本地联调创建的虚构企业。', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('4cd5210f-7701-55a2-8b97-32fa02f799de', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', NULL, 'manual', '项目内置虚构演示数据', NULL, '家庭日常清洁', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('9f77799a-fab4-5808-8364-bbd42401c973', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', NULL, 'manual', '项目内置虚构演示数据', NULL, '家庭用户', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('bc126015-4b07-5798-879a-da3caea4cd2d', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', NULL, 'manual', '项目内置虚构演示数据', NULL, '演示区（虚构地区）', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('d93ddfb8-0ec3-5b23-beb7-c81ae944a2dc', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', NULL, 'manual', '项目内置虚构演示数据', NULL, '清洁范围说明与物品整理建议', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;
INSERT INTO public.evidence (id, client_id, material_id, source_type, source_label, source_url, quote, observed_at, authorization_status) VALUES ('ce1a72a6-1be6-54c5-aa3e-f7e3a6ccc640', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', NULL, 'manual', '项目内置虚构演示数据', NULL, '不得宣称全市第一、保证效果或保证收录；不得把本演示数据当作真实经营信息。', '2026-10-15', 'authorized') ON CONFLICT DO NOTHING;


--
-- Data for Name: facts; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('44d8d8cf-3225-585c-8d1c-2c2951761835', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'identity', 'identity.introduction', '企业介绍', '演示星光美术（虚构）是为本地联调创建的虚构企业。', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('a41def79-6c53-5b6c-840c-de2d8bb8033b', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'service', 'service.primary', '核心服务', '美术体验课程', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('19d5ee48-1f03-55d0-8056-c9f82b1bccf1', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'audience', 'audience.primary', '服务对象', '儿童及家长', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('11f292be-532c-574e-804d-5e12bcc877db', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'location', 'location.service_area', '服务范围', '演示区（虚构地区）', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('63b4f228-cc08-5f62-9dc2-589ff8849498', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'capability', 'capability.primary', '服务说明', '小班体验与绘画材料说明', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('579650a5-7411-5824-9ff2-3be85f3b3a76', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'compliance', 'compliance.prohibited', '禁止使用的说法', '不得宣称全市第一、保证效果或保证收录；不得把本演示数据当作真实经营信息。', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('d54b753f-3621-5ba4-af79-32c28b2fcda0', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'identity', 'identity.introduction', '企业介绍', '演示安心家政（虚构）是为本地联调创建的虚构企业。', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('e4d4c486-b3dd-520c-8b66-fbb4f4c11d98', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'service', 'service.primary', '核心服务', '家庭日常清洁', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('315c93b6-874d-51a2-beaf-67b254960937', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'audience', 'audience.primary', '服务对象', '家庭用户', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('25fc6c3c-4460-56a2-9c4a-f06c6e901cdf', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'location', 'location.service_area', '服务范围', '演示区（虚构地区）', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('46120dc6-a757-5f1d-99c7-19026849bd04', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'capability', 'capability.primary', '服务说明', '清洁范围说明与物品整理建议', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.facts (id, client_id, category, key, label, value, status, confidence, valid_from, valid_until, confirmation_note, version, updated_at) VALUES ('b102eb7f-bc4c-52fa-86f0-09784c6b56cb', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'compliance', 'compliance.prohibited', '禁止使用的说法', '不得宣称全市第一、保证效果或保证收录；不得把本演示数据当作真实经营信息。', 'confirmed', 100, NULL, NULL, '虚构样例，仅供隔离开发环境演示，不代表真实核验。', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;


--
-- Data for Name: fact_evidence; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('44d8d8cf-3225-585c-8d1c-2c2951761835', '423a83e7-75b3-5991-b447-fabbc4f567c5') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('a41def79-6c53-5b6c-840c-de2d8bb8033b', '7281ac45-e9c4-5f7b-ab64-ec9cc9ca8b4a') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('19d5ee48-1f03-55d0-8056-c9f82b1bccf1', 'f3811123-eb52-5a6d-a5e5-429c2887d3f2') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('11f292be-532c-574e-804d-5e12bcc877db', 'df2ffce9-37ab-5c3c-8c7d-14d00b3de242') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('63b4f228-cc08-5f62-9dc2-589ff8849498', '557c2153-00df-5218-b50b-dacdd74215e1') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('579650a5-7411-5824-9ff2-3be85f3b3a76', 'd083e286-caf0-525c-9eba-7723ee58c829') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('d54b753f-3621-5ba4-af79-32c28b2fcda0', '63cad0d7-d499-5b65-b68a-aaf24e884d9e') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('e4d4c486-b3dd-520c-8b66-fbb4f4c11d98', '4cd5210f-7701-55a2-8b97-32fa02f799de') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('315c93b6-874d-51a2-beaf-67b254960937', '9f77799a-fab4-5808-8364-bbd42401c973') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('25fc6c3c-4460-56a2-9c4a-f06c6e901cdf', 'bc126015-4b07-5798-879a-da3caea4cd2d') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('46120dc6-a757-5f1d-99c7-19026849bd04', 'd93ddfb8-0ec3-5b23-beb7-c81ae944a2dc') ON CONFLICT DO NOTHING;
INSERT INTO public.fact_evidence (fact_id, evidence_id) VALUES ('b102eb7f-bc4c-52fa-86f0-09784c6b56cb', 'ce1a72a6-1be6-54c5-aa3e-f7e3a6ccc640') ON CONFLICT DO NOTHING;


--
-- Data for Name: knowledge_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.knowledge_profiles (client_id, services, capabilities, prohibited_claims, external_presences, version, updated_at) VALUES ('1c94477f-ed71-58c3-a3a3-c438f4bf3153', '[]', '[]', '[]', '[]', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;
INSERT INTO public.knowledge_profiles (client_id, services, capabilities, prohibited_claims, external_presences, version, updated_at) VALUES ('56a9ea16-4b83-5bf1-8f09-2d3817fd3407', '[]', '[]', '[]', '[]', 1, '2026-10-15 00:00:00+00') ON CONFLICT DO NOTHING;


--
-- Data for Name: strategy_bundles; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.strategy_bundles (id, client_id, diagnostic_run_id, generated_at, version, prompt_template_code, prompt_template_version) VALUES ('4221490d-86b5-5939-ae4d-7de2bca35e92', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', NULL, '2026-10-15 00:00:00+00', 1, NULL, NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.strategy_bundles (id, client_id, diagnostic_run_id, generated_at, version, prompt_template_code, prompt_template_version) VALUES ('6ae27f78-6a5c-56eb-929f-5c3220f02ba0', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', NULL, '2026-10-15 00:00:00+00', 1, NULL, NULL) ON CONFLICT DO NOTHING;


--
-- Data for Name: strategy_items; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.strategy_items (id, bundle_id, client_id, kind, text, family, keyword_type, provenance, target_level, priority, rationale, locked, active, version, main_keyword, user_intent, selected, recommended_content_type) VALUES ('ec0fac41-b342-5dfc-9cf1-1171b4c44af5', '4221490d-86b5-5939-ae4d-7de2bca35e92', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'keyword', '演示区美术体验课程', NULL, 'local_service', 'manual', 'L1', 2, '手工编写的虚构演示关键词，非模型分析结果。', true, true, 1, '美术体验课程', '了解虚构演示服务', true, 'selection_guide') ON CONFLICT DO NOTHING;
INSERT INTO public.strategy_items (id, bundle_id, client_id, kind, text, family, keyword_type, provenance, target_level, priority, rationale, locked, active, version, main_keyword, user_intent, selected, recommended_content_type) VALUES ('632ef595-1e79-54e9-8ed9-26ed17770c05', '4221490d-86b5-5939-ae4d-7de2bca35e92', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'keyword', '美术体验课怎么准备', NULL, 'service_detail', 'manual', 'L1', 2, '手工编写的虚构演示关键词，非模型分析结果。', true, true, 1, '美术体验课程', '了解虚构演示服务', true, 'selection_guide') ON CONFLICT DO NOTHING;
INSERT INTO public.strategy_items (id, bundle_id, client_id, kind, text, family, keyword_type, provenance, target_level, priority, rationale, locked, active, version, main_keyword, user_intent, selected, recommended_content_type) VALUES ('c29b081f-95e2-57ce-bea5-e2864140012c', '4221490d-86b5-5939-ae4d-7de2bca35e92', '1c94477f-ed71-58c3-a3a3-c438f4bf3153', 'keyword', '如何比较美术课程', NULL, 'comparison', 'manual', 'L1', 2, '手工编写的虚构演示关键词，非模型分析结果。', true, true, 1, '美术体验课程', '了解虚构演示服务', true, 'selection_guide') ON CONFLICT DO NOTHING;
INSERT INTO public.strategy_items (id, bundle_id, client_id, kind, text, family, keyword_type, provenance, target_level, priority, rationale, locked, active, version, main_keyword, user_intent, selected, recommended_content_type) VALUES ('ec7a4200-fa2f-5585-99a6-723bd1c2ebe3', '6ae27f78-6a5c-56eb-929f-5c3220f02ba0', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'keyword', '演示区家庭清洁', NULL, 'local_service', 'manual', 'L1', 2, '手工编写的虚构演示关键词，非模型分析结果。', true, true, 1, '家庭日常清洁', '了解虚构演示服务', true, 'selection_guide') ON CONFLICT DO NOTHING;
INSERT INTO public.strategy_items (id, bundle_id, client_id, kind, text, family, keyword_type, provenance, target_level, priority, rationale, locked, active, version, main_keyword, user_intent, selected, recommended_content_type) VALUES ('d15c45bb-1bae-50f5-b64b-6bb1e28dff52', '6ae27f78-6a5c-56eb-929f-5c3220f02ba0', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'keyword', '家庭清洁服务包含什么', NULL, 'service_detail', 'manual', 'L1', 2, '手工编写的虚构演示关键词，非模型分析结果。', true, true, 1, '家庭日常清洁', '了解虚构演示服务', true, 'selection_guide') ON CONFLICT DO NOTHING;
INSERT INTO public.strategy_items (id, bundle_id, client_id, kind, text, family, keyword_type, provenance, target_level, priority, rationale, locked, active, version, main_keyword, user_intent, selected, recommended_content_type) VALUES ('c2bbb56b-df4b-5da7-813e-d1e4de4e2e19', '6ae27f78-6a5c-56eb-929f-5c3220f02ba0', '56a9ea16-4b83-5bf1-8f09-2d3817fd3407', 'keyword', '如何比较家政服务', NULL, 'comparison', 'manual', 'L1', 2, '手工编写的虚构演示关键词，非模型分析结果。', true, true, 1, '家庭日常清洁', '了解虚构演示服务', true, 'selection_guide') ON CONFLICT DO NOTHING;


--
-- PostgreSQL database dump complete
--
