#!/usr/bin/env python3
"""Chuyển dữ liệu từ db.sqlite3 của bản monolith sang các database MySQL của từng service.

  user_db       <- auth_user, app_userprofile
  catalog_db    <- app_category, app_product, app_review (+ username lấy từ auth_user)
  order_db      <- app_order, app_orderitem (+ snapshot khuyến mãi / tên & giá sản phẩm cho đơn đã hoàn tất)
  promotion_db  <- app_promotion (+ app_promotion_products/categories -> product_ids/category_ids)

Giữ nguyên ID (để các tham chiếu chéo service vẫn đúng) và password hash (người dùng đăng nhập như cũ).
Cần chạy SAU khi các service đã chạy migrate (bảng đã tồn tại). Dùng tài khoản MySQL có quyền trên cả 4 DB (vd. root).

Cách dùng:
  python migrate_sqlite_to_mysql.py --sqlite /path/db.sqlite3 --host 127.0.0.1 --user root --password ...
  (thêm --truncate nếu muốn xóa dữ liệu đang có trong các bảng đích trước khi nạp; thêm --dry-run để chỉ thống kê)
"""
import argparse
import json
import sqlite3
import sys
import uuid

import pymysql


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sqlite", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", default="root")
    p.add_argument("--password", default="")
    p.add_argument("--user-db", default="user_db")
    p.add_argument("--catalog-db", default="catalog_db")
    p.add_argument("--order-db", default="order_db")
    p.add_argument("--promotion-db", default="promotion_db")
    p.add_argument("--truncate", action="store_true", help="xóa dữ liệu trong bảng đích trước khi nạp")
    p.add_argument("--dry-run", action="store_true", help="chỉ in thống kê, không ghi gì")
    return p.parse_args()


def connect(args, db):
    return pymysql.connect(host=args.host, port=args.port, user=args.user, password=args.password,
                           database=db, charset="utf8mb4", autocommit=False)


def insert(cur, table, rows, columns):
    if not rows:
        return 0
    sql = f"INSERT INTO `{table}` ({', '.join('`'+c+'`' for c in columns)}) VALUES ({', '.join(['%s']*len(columns))})"
    cur.executemany(sql, [[r[c] for c in columns] for r in rows])
    return len(rows)


def prepare_target(cur, tables, truncate):
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM `{t}`")
        n = cur.fetchone()[0]
        if n and not truncate:
            sys.exit(f"Bảng {t} đã có {n} dòng. Dùng --truncate nếu muốn ghi đè.")
        if n:
            cur.execute(f"DELETE FROM `{t}`")


def main():
    args = parse_args()
    src = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    q = lambda sql, *a: [dict(r) for r in src.execute(sql, a)]  # noqa: E731
    report = {}

    # ---------- đọc nguồn ----------
    users = q("SELECT * FROM auth_user")
    profiles = q("SELECT * FROM app_userprofile")
    categories = q("SELECT * FROM app_category")
    products = q("SELECT * FROM app_product")
    reviews = q("SELECT * FROM app_review")
    promos = q("SELECT * FROM app_promotion")
    promo_products, promo_cats = {}, {}
    for r in q("SELECT promotion_id, product_id FROM app_promotion_products"):
        promo_products.setdefault(r["promotion_id"], []).append(r["product_id"])
    for r in q("SELECT promotion_id, category_id FROM app_promotion_categories"):
        promo_cats.setdefault(r["promotion_id"], []).append(r["category_id"])
    orders = q("SELECT * FROM app_order ORDER BY id")
    items = q("SELECT * FROM app_orderitem ORDER BY id")

    username_by_id = {u["id"]: u["username"] for u in users}
    promo_by_id = {p["id"]: p for p in promos}
    product_by_id = {p["id"]: p for p in products}

    # ---------- user_db ----------
    user_rows = [{k: u[k] for k in ("id", "password", "last_login", "is_superuser", "username", "first_name",
                                     "last_name", "email", "is_staff", "is_active", "date_joined")} for u in users]
    # SQLite cho phép NULL trong cột NOT NULL cũ; MySQL strict thì không -> chuẩn hóa về chuỗi rỗng.
    profile_rows = [{"id": p["id"], "user_id": p["user_id"], "full_name": p["full_name"] or "",
                     "phone": p["phone"] or "", "address": p["address"] or ""}
                    for p in profiles if p["user_id"] in username_by_id]

    # ---------- catalog_db ----------
    category_rows = [{k: c[k] for k in ("id", "name", "slug")} for c in categories]
    product_cols = ("id", "name", "slug", "description", "price", "unit", "stock", "status", "origin", "image",
                    "is_featured", "created_at", "updated_at", "category_id", "user_id")
    product_rows = [{k: p[k] for k in product_cols} for p in products]
    review_rows = [{"id": r["id"], "rating": r["rating"], "comment": r["comment"], "created_at": r["created_at"],
                    "product_id": r["product_id"], "user_id": r["user_id"], "parent_id": r["parent_id"],
                    "username": username_by_id.get(r["user_id"], "unknown")} for r in reviews]
    # cha phải được chèn trước con (có FK tự tham chiếu)
    review_rows.sort(key=lambda r: (r["parent_id"] is not None, r["id"]))

    # ---------- promotion_db ----------
    promo_rows = [{
        "id": p["id"], "user_id": p["user_id"], "name": p["name"], "code": p["code"],
        "discount_type": p["discount_type"], "discount_value": p["discount_value"], "apply_type": p["apply_type"],
        "product_ids": json.dumps(sorted(promo_products.get(p["id"], []))),
        "category_ids": json.dumps(sorted(promo_cats.get(p["id"], []))),
        "start_date": p["start_date"], "end_date": p["end_date"], "is_active": p["is_active"],
        "min_order_value": p["min_order_value"] or 0,
    } for p in promos]

    # ---------- order_db ----------
    items_by_order = {}
    orphan_items = 0
    for it in items:
        if it["order_id"] is None or it["product_id"] is None:
            orphan_items += 1
            continue
        bucket = items_by_order.setdefault(it["order_id"], {})
        if it["product_id"] in bucket:  # gộp dòng trùng sản phẩm (ràng buộc unique order+product)
            bucket[it["product_id"]]["quantity"] = (bucket[it["product_id"]]["quantity"] or 0) + (it["quantity"] or 0)
        else:
            bucket[it["product_id"]] = dict(it)

    order_rows, item_rows, skipped_empty_guest = [], [], 0
    for o in orders:
        complete = bool(o["complete"])
        o_items = items_by_order.get(o["id"], {})
        if not complete and o["customer_id"] is None and not o_items:
            skipped_empty_guest += 1  # giỏ trống của khách vãng lai: rác, không cần chuyển
            continue
        tx = o["transaction_id"] or ""
        guest_token = None
        if o["customer_id"] is None and not complete:
            guest_token = tx if len(tx) == 32 else None  # transaction_id của giỏ khách vãng lai chính là session key
            tx = "GM" + uuid.uuid4().hex[:10].upper()
        elif not tx:
            tx = "GM" + uuid.uuid4().hex[:10].upper()
        row = {"id": o["id"], "customer_id": o["customer_id"], "guest_token": guest_token,
               "date_order": o["date_order"], "complete": o["complete"], "transaction_id": tx,
               "promotion_id": None, "promotion_code": None, "promotion_name": None,
               "promotion_discount_type": None, "promotion_apply_type": None,
               "promotion_discount_value": None, "promotion_min_order_value": None}
        p = promo_by_id.get(o["promotion_id"])
        if p:
            row.update(promotion_id=p["id"], promotion_code=p["code"], promotion_name=p["name"],
                       promotion_discount_type=p["discount_type"], promotion_apply_type=p["apply_type"],
                       promotion_discount_value=p["discount_value"], promotion_min_order_value=p["min_order_value"] or 0)
        order_rows.append(row)
        for it in o_items.values():
            prod = product_by_id.get(it["product_id"])
            snap = complete and prod is not None
            item_rows.append({
                "id": it["id"], "order_id": o["id"], "product_id": it["product_id"],
                "quantity": it["quantity"], "date_added": it["date_added"],
                # đơn đã hoàn tất: chốt tên/giá theo giá hiện tại của sản phẩm (dữ liệu cũ không lưu giá lúc mua)
                "product_name": prod["name"] if snap else "", "product_slug": prod["slug"] if snap else "",
                "unit_price": prod["price"] if snap else None,
            })

    report.update({
        "user_db.auth_user": len(user_rows), "user_db.userprofile": len(profile_rows),
        "catalog_db.category": len(category_rows), "catalog_db.product": len(product_rows),
        "catalog_db.review": len(review_rows), "promotion_db.promotion": len(promo_rows),
        "order_db.order": len(order_rows), "order_db.orderitem": len(item_rows),
        "bỏ qua: giỏ khách vãng lai trống": skipped_empty_guest, "bỏ qua: order item mồ côi": orphan_items,
    })
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    # ---------- ghi đích ----------
    targets = [
        (args.user_db, [("auth_user", user_rows, ("id", "password", "last_login", "is_superuser", "username",
                                                    "first_name", "last_name", "email", "is_staff", "is_active", "date_joined")),
                        ("accounts_userprofile", profile_rows, ("id", "full_name", "phone", "address", "user_id"))]),
        (args.catalog_db, [("catalog_category", category_rows, ("id", "name", "slug")),
                           ("catalog_product", product_rows, product_cols),
                           ("catalog_review", review_rows, ("id", "rating", "comment", "created_at", "product_id",
                                                             "user_id", "username", "parent_id"))]),
        (args.promotion_db, [("promotions_promotion", promo_rows, ("id", "user_id", "name", "code", "discount_type",
                                                                   "discount_value", "apply_type", "product_ids",
                                                                   "category_ids", "start_date", "end_date",
                                                                   "is_active", "min_order_value"))]),
        (args.order_db, [("orders_order", order_rows, tuple(order_rows[0].keys()) if order_rows else ()),
                         ("orders_orderitem", item_rows, ("id", "order_id", "product_id", "quantity", "date_added",
                                                           "product_name", "product_slug", "unit_price"))]),
    ]
    for db, tables in targets:
        conn = connect(args, db)
        try:
            cur = conn.cursor()
            # xóa theo thứ tự ngược (con trước cha)
            prepare_target(cur, [t for t, _, _ in reversed(tables)], args.truncate)
            for table, rows, cols in tables:
                n = insert(cur, table, rows, cols)
                print(f"  {db}.{table}: {n} dòng")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    print("\nTổng kết:")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
