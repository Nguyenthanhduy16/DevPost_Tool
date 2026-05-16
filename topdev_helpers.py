"""Helper functions for TopDev job posting automation (Sync version)."""
import time
import pandas as pd
import os

# ── Logging ──────────────────────────────────────────────────────────────────
def log_step(step: str, detail: str = ""):
    print(f"\n{'─'*55}")
    print(f"📌 {step}")
    if detail:
        print(f"   {detail}")

def log_ok(msg: str):
    print(f"  ✅ {msg}")

def log_err(msg: str, exc=None):
    detail = f"\n     └─ {str(exc)[:150]}" if exc else ""
    print(f"  ❌ {msg}{detail}")

def log_info(msg: str):
    print(f"  ⏳ {msg}")

def log_skip(msg: str):
    print(f"  ⚠️  Bỏ qua: {msg}")

# ── Excel reader ──────────────────────────────────────────────────────────────
def read_excel(filepath: str) -> list:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Không tìm thấy file: {filepath}")
    df = pd.read_excel(filepath, dtype=str)
    df = df.fillna("")
    # Lọc bỏ dòng không có title (thử cả 2 tên cột)
    for col in ["Tên hiển thị trên website MB", "Job Title", "Vị trí (HCM)"]:
        if col in df.columns:
            df = df[df[col].str.strip() != ""]
            break
    jobs = df.to_dict(orient="records")
    print(f"✅ Đọc được {len(jobs)} tin tuyển dụng từ {filepath}")
    return jobs


COL_TITLE   = "Tên hiển thị trên website MB"
COL_TINH    = "Tỉnh"
COL_SAL_MIN = "LƯƠNG MIN"
COL_SAL_MAX = "LƯƠNG MAX"

def preview_jobs(jobs: list):
    print(f"\n{'#'*55}")
    print(f"  DANH SÁCH JD ({len(jobs)} tin)")
    print(f"{'#'*55}")
    for i, j in enumerate(jobs):
        title = j.get(COL_TITLE, j.get('Job Title', '(trống)'))
        print(f"  [{i}] {str(title)[:70]}")
        print(f"       📍 {j.get(COL_TINH,'')}  |  💰 {j.get(COL_SAL_MIN,'')} – {j.get(COL_SAL_MAX,'')}")
    print()

# ── Sync Automation helpers ──────────────────────────────────────────────────
def safe_fill(page, selector: str, value: str, label: str = ""):
    """Điền text vào input, báo lỗi nếu không tìm được."""
    value = str(value).strip()
    if not value:
        log_skip(label or selector)
        return False
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=5000)
        el.click()
        el.fill("")
        el.fill(value)
        log_ok(f"{label}: {value[:60]}")
        return True
    except Exception as e:
        log_err(f"{label}: {value[:60]}", e)
        return False


def select_react_dropdown(page, label_text: str, value: str, timeout: int = 6000):
    """Chọn từ React Select dropdown."""
    value = str(value).strip()
    if not value:
        log_skip(label_text)
        return False
    log_info(f"Đang chọn {label_text}: {value}")
    try:
        # Tìm tất cả các label trên trang
        labels = page.locator("label")
        target_label = None
        count = labels.count()
        for i in range(count):
            txt = (labels.nth(i).text_content() or "").strip()
            if label_text.lower() in txt.lower():
                target_label = labels.nth(i)
                break

        if target_label is None:
            log_err(f"Không tìm thấy label '{label_text}'")
            return False

        # Tìm container cha chứa cả label và select
        parent = target_label.locator("xpath=..")
        # Tìm react-select control trong parent hoặc siblings
        control = parent.locator("[class*='control'], [class*='select']").first
        try:
            control.wait_for(state="visible", timeout=3000)
        except Exception:
            # Thử tìm ở parent level cao hơn
            parent = parent.locator("xpath=..")
            control = parent.locator("[class*='control'], [class*='select']").first
            control.wait_for(state="visible", timeout=3000)

        control.click()
        time.sleep(0.5)

        # Gõ vào input bên trong react-select
        active_input = page.locator("[class*='menu'] ~ input, [class*='select'] input[type='text'], input:focus").first
        try:
            active_input.fill(value)
        except Exception:
            page.keyboard.type(value, delay=40)
        time.sleep(0.8)

        # Click option
        option = page.locator(f"[class*='option']").filter(has_text=value).first
        option.click(timeout=timeout)
        time.sleep(0.3)
        log_ok(f"{label_text}: {value}")
        return True
    except Exception as e:
        log_err(f"{label_text}: {value}", e)
        return False


def add_item_with_plus(page, section_text: str, text: str, timeout: int = 5000):
    """Điền text vào input rồi nhấn nút (+) trong section."""
    text = str(text).strip()
    if not text:
        return False
    try:
        # Tìm section chứa text
        # Thử tìm heading chứa keyword
        heading = page.locator(
            f"h3:text-is('{section_text}'), h4:text-is('{section_text}'), "
            f"label:text-is('{section_text}'), "
            f"h3:has-text('{section_text}'), h4:has-text('{section_text}')"
        ).first

        section = heading.locator("xpath=ancestor::div[.//button]").last

        inp = section.locator("input[type='text'], textarea").last
        inp.wait_for(state="visible", timeout=timeout)
        inp.click()
        inp.fill("")
        inp.fill(text)
        time.sleep(0.2)

        btn = section.locator("button").filter(has_text="+").first
        btn.click(timeout=timeout)
        time.sleep(0.3)
        return True
    except Exception as e:
        # Fallback: tìm bằng cách khác
        try:
            section = page.locator(f"div:has(h3:has-text('{section_text}'))").last
            inp = section.locator("input[type='text'], textarea").last
            inp.click()
            inp.fill(text)
            time.sleep(0.2)
            btn = section.locator("button").filter(has_text="+").first
            btn.click(timeout=timeout)
            time.sleep(0.3)
            return True
        except Exception:
            return False


def fill_list_section(page, section_text: str, raw_text: str, section_name: str):
    """Điền nhiều items từ raw_text (mỗi dòng 1 item)."""
    items = [line.strip() for line in str(raw_text).split("\n") if line.strip()]
    if not items:
        log_skip(f"{section_name} (rỗng)")
        return
    log_info(f"Điền {len(items)} {section_name}")
    ok = 0
    for item in items:
        if add_item_with_plus(page, section_text, item):
            ok += 1
            print(f"    ✅ {item[:70]}")
        else:
            print(f"    ❌ {item[:70]}")
    if ok == len(items):
        log_ok(f"{section_name}: {ok}/{len(items)} items")
    else:
        log_err(f"{section_name}: {ok}/{len(items)} items")
