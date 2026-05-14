-- 在 Supabase SQL Editor 里执行一次即可。
-- 1) 存储 zhuiguang.xyz 登录态（Fernet 加密后的字符串）
create table if not exists public.auth_state (
    id text primary key,
    encrypted_state text not null,
    updated_at timestamptz not null default now()
);

-- 2) 抓取日志（可选，方便排查）
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

-- 注意：此服务使用 service_role key 直接访问，请勿对外开放这两张表的 anon 读写。
-- 如果需要在 Supabase 内部启用 RLS，请保持 service_role 绕过策略即可。
