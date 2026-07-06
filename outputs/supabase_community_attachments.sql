-- Community post file attachments.
-- Run this in Supabase SQL Editor before enabling uploads in production.

alter table public.hodu_community_posts
add column if not exists attachments jsonb not null default '[]'::jsonb;

-- The Flask backend uses the service role key to create/upload to this bucket.
-- If you prefer creating it manually, keep the bucket public for the current UI.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'hodu-community',
  'hodu-community',
  true,
  5242880,
  array['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'application/pdf']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
