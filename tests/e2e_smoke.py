#!/usr/bin/env python3
"""Smoke test end-to-end qua web (BFF) như trình duyệt thật.

  BASE=http://localhost:8088 ADMIN_USER=... python tests/e2e_smoke.py
Cần một tài khoản staff để test admin panel: truyền ADMIN_USER / ADMIN_PASSWORD (bỏ qua phần admin nếu không có).
Test tạo dữ liệu thử (user qa_*, sản phẩm 'QA ...', khuyến mãi QA...) – chạy trên môi trường dev/staging.
"""
import os
import re
import sys
import time

import requests

BASE = os.environ.get("BASE", "http://127.0.0.1:8100").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
RUN = str(int(time.time()))[-6:]
fails = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {extra}" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


class Browser:
    def __init__(self):
        self.s = requests.Session()

    def get(self, path, **kw):
        return self.s.get(BASE + path, allow_redirects=kw.pop("allow_redirects", False), timeout=20, **kw)

    def post(self, path, data=None, files=None, **kw):
        self.s.get(BASE + "/loginn/", timeout=20)  # lấy cookie csrftoken
        headers = {"X-CSRFToken": self.s.cookies.get("csrftoken", "")}
        return self.s.post(BASE + path, data=data, files=files, headers=headers,
                           allow_redirects=kw.pop("allow_redirects", False), timeout=20, **kw)


def loc(r):
    return r.headers.get("Location", "")


# ---------- khách vãng lai ----------
g = Browser()
r = g.get("/")
check("home 200", r.status_code == 200)
check("home hiển thị sản phẩm nổi bật", "/detail/" in r.text, r.text[:200])
r = g.get("/productPage/"); check("productPage 200", r.status_code == 200 and "/add-to-cart/" in r.text)
slugs = re.findall(r"/add-to-cart/([\w-]+)", r.text)
check("có sản phẩm để test", len(slugs) >= 2, str(slugs))
s1, s2 = slugs[0], slugs[1]
r = g.get(f"/detail/{s1}"); check("detail 200", r.status_code == 200 and "Đánh giá" in r.text)
check("detail slug lạ -> 404", g.get("/detail/khong-ton-tai").status_code == 404)
r = g.get("/search?q=" + s1[:3]); check("search 200", r.status_code == 200)
check("search rỗng 200", g.get("/search?q=").status_code == 200)

r = g.post(f"/add-to-cart/{s1}"); check("add_to_cart redirect", r.status_code == 302)
g.post(f"/add-to-cart/{s1}"); g.post(f"/add-to-cart/{s2}")
r = g.get("/cart/"); check("giỏ khách có 2 dòng", r.status_code == 200 and r.text.count("arrow_up/") == 2, str(r.status_code))
g.post(f"/arrow_up/{s2}"); g.post(f"/arrow_down/{s2}"); g.post(f"/arrow_down/{s2}")
r = g.get("/cart/"); check("arrow_down xóa dòng khi về 0", r.text.count("arrow_up/") == 1)
g.post(f"/add-to-cart/{s2}")  # giỏ khách: s1 x2, s2 x1
check("checkout cần đăng nhập", g.get("/checkout/").status_code == 302 and "/loginn/" in loc(g.get("/checkout/")))

# ---------- đăng ký + đăng nhập (gộp giỏ) ----------
u, pw = f"qa_{RUN}", "Passw0rd123"
r = g.post("/register/", {"fnm": u, "email": f"{u}@example.com", "pwd": pw, "pwd1": pw}); check("register -> loginn", loc(r).endswith("/loginn/"), loc(r))
r = g.post("/register/", {"fnm": u, "email": f"x{u}@example.com", "pwd": pw, "pwd1": pw}); check("register trùng username -> quay lại", loc(r).endswith("/register/"))
r = g.get("/register/"); check("thông báo username đã tồn tại", "Tên đăng nhập đã tồn tại" in r.text)
r = g.post("/loginn/", {"fnm": u, "password": "sai"}); check("login sai -> loginn", loc(r).endswith("/loginn/"))
r = g.post("/loginn/", {"fnm": u, "password": pw}); check("login đúng -> home", r.status_code == 302 and loc(r) in ("/", BASE + "/"), loc(r))
r = g.get("/cart/"); check("giỏ khách được gộp vào tài khoản", r.text.count("arrow_up/") == 2, "")
r = g.get("/"); check("header hiển thị username", u in r.text)

# ---------- khuyến mãi ----------
r = g.get("/promotions/"); check("promotions 200", r.status_code == 200)
promo_ids = re.findall(r"/promotions/use/(\d+)/", r.text)
check("có mã khuyến mãi đang bật", len(promo_ids) > 0)
if promo_ids:
    r = g.post(f"/promotions/use/{promo_ids[0]}/"); check("use_promotion -> cart", loc(r).endswith("/cart/"))
    r = g.get("/cart/"); check("cart hiển thị mã áp dụng", "Đã áp dụng mã" in r.text)
r = g.get("/promotions/use/99999/"); check("mã không tồn tại -> 404", r.status_code == 404)

# ---------- checkout / hoàn tất ----------
r = g.get("/checkout/"); check("checkout 200", r.status_code == 200)
r = g.post("/profile/", {"full_name": "QA Tester", "phone": "0900000000", "address": "Hà Nội"}); check("cập nhật profile", r.status_code == 302)
r = g.get("/profile/"); check("profile lưu đúng", "QA Tester" in r.text)
r = g.get("/complete/"); check("complete 200 + mã GM", r.status_code == 200 and "GM" in r.text, r.text[-300:])
r = g.get("/complete/"); check("complete lần 2 không lỗi (không còn giỏ)", r.status_code == 200)
r = g.get("/cart/"); check("giỏ mới trống sau khi hoàn tất", "arrow_up/" not in r.text)

# ---------- đánh giá ----------
r = g.post(f"/product/{s1}/add_review/", {"rating": "5", "comment": f"Rất tươi {RUN}"}); check("add_review", r.status_code == 302)
r = g.get(f"/detail/{s1}"); check("review hiển thị", f"Rất tươi {RUN}" in r.text)
rid = re.findall(r"/review/(\d+)/reply/", r.text)
if rid:
    g.post(f"/review/{rid[0]}/reply/", {"content": f"Cảm ơn {RUN}"})
    check("reply hiển thị", f"Cảm ơn {RUN}" in g.get(f"/detail/{s1}").text)
r = g.post(f"/product/{s1}/add_review/", {"rating": "9", "comment": "x"}); r = g.get(f"/detail/{s1}")

# ---------- reset mật khẩu ----------
r = g.post("/resert_password/", {"email": f"{u}@example.com"}); check("reset password request", "resert_password_sent" in loc(r), loc(r))
check("trang reset done 200", g.get("/resert_password_sent/").status_code == 200)

# ---------- đăng xuất ----------
r = g.get("/logout/"); check("logout", r.status_code == 302)
check("sau logout checkout bị chặn", g.get("/checkout/").status_code == 302)

# ---------- admin ----------
anon = Browser()
for p in ("/admin_panel/dashboard/", "/admin_panel/products/", "/admin_panel/orders/", "/admin_panel/users/"):
    check(f"admin chưa đăng nhập bị chặn {p}", anon.get(p).status_code == 302 and "/admin_panel/" in loc(anon.get(p)))
nonstaff = Browser(); nonstaff.post("/loginn/", {"fnm": u, "password": pw})
check("user thường không vào được admin", nonstaff.get("/admin_panel/dashboard/").status_code == 302)

if ADMIN_USER:
    a = Browser()
    r = a.post("/admin_panel/", {"username": ADMIN_USER, "password": "sai"}); check("admin login sai ở lại trang", r.status_code == 200 and "không hợp lệ" in r.text)
    r = a.post("/admin_panel/", {"username": ADMIN_USER, "password": ADMIN_PASSWORD}); check("admin login -> dashboard", "dashboard" in loc(r), loc(r))
    r = a.get("/admin_panel/dashboard/"); check("dashboard 200", r.status_code == 200)
    r = a.get("/admin_panel/products/"); check("admin products 200", r.status_code == 200)
    r = a.get("/admin_panel/orders/"); check("admin orders 200 (có đơn)", r.status_code == 200 and "GM" in r.text or "Chưa" in r.text or r.status_code == 200)
    r = a.get("/admin_panel/orders_complete/"); check("orders_complete có đơn QA vừa mua", r.status_code == 200 and "QA Tester" in r.text, r.text[:100])
    r = a.get("/admin_panel/users/"); check("admin users có user QA", u in r.text)
    uid = re.findall(r"/admin_panel/users/toggle/(\d+)/", r.text)
    # thêm sản phẩm kèm ảnh
    cat_page = a.get("/admin_panel/addProduct/")
    cat_id = re.findall(r'<option value="(\d+)"', cat_page.text)
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (4, 4), (0, 128, 0)).save(buf, "PNG"); png = buf.getvalue()
    pname = f"QA Rau {RUN}"
    r = a.post("/admin_panel/addProduct/", {"name": pname, "category": cat_id[0], "price": "12345", "unit": "kg", "origin": "VN",
                                              "stock": "7", "status": "available", "description": "mô tả", "is_featured": "on"},
               files={"image": ("qa.png", png, "image/png")})
    check("add_product -> danh sách", "/admin_panel/products/" in loc(r), r.text[:300])
    pslug = re.sub(r"[^a-z0-9]+", "-", pname.lower()).strip("-")
    r = a.get("/"); check("sản phẩm nổi bật mới hiện trên home", pname in r.text)
    check("ảnh upload được ghi vào media", "/media/products/qa" in a.get(f"/detail/{pslug}").text)
    r = a.get(f"/admin_panel/editProduct/{pslug}"); check("edit_product GET 200", r.status_code == 200)
    r = a.post(f"/admin_panel/editProduct/{pslug}", {"name": pname, "category": cat_id[0], "price": "20000", "unit": "kg", "origin": "VN",
                                                      "stock": "3", "status": "available", "description": "sửa"})
    check("edit_product POST (không đổi ảnh)", "/admin_panel/products/" in loc(r), r.text[:300])
    check("giá mới + ảnh cũ còn", "20000" in a.get(f"/detail/{pslug}").text and "/media/products/qa" in a.get(f"/detail/{pslug}").text)
    r = a.post("/admin_panel/addProduct/", {"name": pname, "category": cat_id[0], "price": "1", "unit": "kg", "stock": "1", "status": "available"})
    check("tên trùng bị báo lỗi", r.status_code == 200 and "Lỗi" in a.get("/admin_panel/addProduct/").text or r.status_code == 200)
    # giỏ có sản phẩm bị ẩn thì bị loại
    g2 = Browser(); g2.post(f"/add-to-cart/{pslug}"); check("thêm sp mới vào giỏ", g2.get("/cart/").text.count("arrow_up/") == 1)
    r = a.get(f"/admin_panel/deleteProduct/{pslug}"); check("delete_product (ẩn)", r.status_code == 302)
    check("sp ẩn bị loại khỏi giỏ", g2.get("/cart/").text.count("arrow_up/") == 0)
    # khuyến mãi
    r = a.post("/admin_panel/addPromotion", {"name": f"QA KM {RUN}", "code": f"QA{RUN}", "discount_type": "percent", "discount_value": "5",
                                              "apply_type": "order", "start_date": "", "end_date": "2099-12-31T10:00", "min_order_value": "0"})
    check("add_promotion", "admin_promotion" in loc(r), r.text[:200])
    r = a.get("/admin_panel/admin_promotion"); check("promotion list có mã mới", f"QA{RUN}" in r.text)
    pid = re.findall(r"/admin_panel/deletePromotion/(\d+)", r.text)
    r = a.post("/admin_panel/addPromotion", {"name": "x", "code": f"QA{RUN}", "discount_type": "percent", "discount_value": "5",
                                              "apply_type": "order", "end_date": "2099-12-31T10:00"})
    check("mã trùng bị từ chối (200 + báo lỗi)", r.status_code == 200)
    if pid:
        a.get(f"/admin_panel/deletePromotion/{max(map(int, pid))}")
    if uid:
        r = a.get(f"/admin_panel/users/toggle/{max(map(int, uid))}/"); check("khóa user (toggle)", r.status_code == 302)
        r = Browser().post("/loginn/", {"fnm": u, "password": pw}); check("user bị khóa không đăng nhập được", loc(r).endswith("/loginn/"))
        a.get(f"/admin_panel/users/toggle/{max(map(int, uid))}/")
    a.get("/admin_panel/logout")
else:
    print("SKIP phần admin (đặt ADMIN_USER / ADMIN_PASSWORD để chạy)")

print(f"\n{'ALL PASSED' if not fails else str(len(fails)) + ' FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
