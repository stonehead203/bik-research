create table if not exists public.hodu_community_likes (
  post_id text not null,
  username text not null,
  created_at timestamptz not null default now(),
  primary key (post_id, username)
);

create index if not exists hodu_community_likes_username_idx
  on public.hodu_community_likes (username, created_at desc);

create index if not exists hodu_community_likes_post_id_idx
  on public.hodu_community_likes (post_id);
