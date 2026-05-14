-- 在 Supabase SQL Editor 里执行一次即可。
-- 1) 存储 zhuiguang.xyz 登录态（Fernet 加密后的字符串）
create table if not exists public.auth_state (
    id text primary key,
    encrypted_state text not null,
    updated_at timestamptz not null default now()
);

-- 2) 抓取日志（兼作 keepalive 心跳记录，避免 7 天闲置后 Supabase 自动 pause）
create table if not exists public.scrape_log (
    id bigserial primary key,
    record_id text,
    url text,
    status text,
    message text,
    payload jsonb,
    created_at timestamptz not null default now()
);

create index if not exists scrape_log_record_id_idx on public.scrape_log (record_id);
create index if not exists scrape_log_created_at_idx on public.scrape_log (created_at desc);

-- 显式 GRANT：从 2026-05-30 起新项目默认不再把 public 表暴露给 Data API；
-- 2026-10-30 起所有项目也按这个规则执行。我们通过 supabase-py（PostgREST）
-- 用 service_role 读写这两张表，所以必须把 service_role 的权限明写出来。
grant select, insert, update, delete on public.auth_state to service_role;
grant select, insert, update, delete on public.scrape_log to service_role;
grant usage, select on sequence public.scrape_log_id_seq to service_role;

-- 开启 RLS，并且只允许 service_role 绕过；anon/authenticated 默认拒绝。
alter table public.auth_state enable row level security;
alter table public.scrape_log enable row level security;

-- service_role 在 supabase-py 中已自动绕过 RLS，不需要额外 policy。
-- 不要给 anon / authenticated 任何 grant，这两张表不应被前端读写。
