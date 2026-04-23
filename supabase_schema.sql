-- 請在 Supabase Dashboard > SQL Editor 貼上並執行

create table vendors (
  id serial primary key,
  name text not null,
  created_at timestamptz default now()
);

create table products (
  id serial primary key,
  vendor_id integer references vendors(id) on delete cascade,
  name text not null,
  qty integer not null default 0,
  note text default '',
  created_at timestamptz default now()
);

create table logs (
  id serial primary key,
  product_id integer references products(id) on delete cascade,
  operation text not null,
  qty_change integer not null default 0,
  note text default '',
  logged_at text not null
);

-- 範例資料（可選）
insert into vendors (name) values ('台灣食品股份'), ('大和物流');
